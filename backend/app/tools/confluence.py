"""
Confluence tools — read and write Confluence pages.
Write tools (Create, UpdateSection, AppendSection) are only registered
when CONFLUENCE_WRITE_ENABLED=true in config.
"""
from contextlib import contextmanager
from typing import Optional

import markdown2
import requests
from atlassian import Confluence
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field

from app.config import settings
from app.tools.base import LoggedTool

_PLACEHOLDER_PATTERNS = ("your-company", "example.atlassian", "placeholder", "acme.atlassian")

_NOT_CONFIGURED_MSG = (
    "CONFLUENCE_NOT_CONFIGURED: Confluence integration is not available. "
    "The environment variables CONFLUENCE_URL, CONFLUENCE_USER, and CONFLUENCE_API_TOKEN "
    "must be set to real Confluence credentials. "
    "Do not retry this task — inform the user that Confluence must be configured first."
)


def _get_client() -> Confluence:
    url = settings.CONFLUENCE_URL or ""
    user = settings.CONFLUENCE_USER or ""
    token = settings.CONFLUENCE_API_TOKEN or ""

    if not url or not user or not token:
        raise RuntimeError(_NOT_CONFIGURED_MSG)

    if any(p in url for p in _PLACEHOLDER_PATTERNS):
        raise RuntimeError(
            f"CONFLUENCE_NOT_CONFIGURED: CONFLUENCE_URL '{url}' is a placeholder, not a real URL. "
            "Update it with your actual Confluence URL. "
            "Do not retry this task — inform the user that Confluence must be configured first."
        )

    return Confluence(url=url, username=user, password=token, cloud=True)


@contextmanager
def _confluence_errors():
    """Catch all Confluence/HTTP/connection errors and return a clear message instead of raising."""
    try:
        yield
    except RuntimeError:
        raise  # already formatted — let LoggedTool handle it
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            f"CONFLUENCE_UNREACHABLE: Cannot connect to Confluence ({e}). "
            "Check CONFLUENCE_URL and network access. Do not retry."
        ) from e
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        if status == 401:
            msg = "Invalid credentials — check CONFLUENCE_USER and CONFLUENCE_API_TOKEN."
        elif status == 403:
            msg = "Access denied — the API token may lack required permissions."
        elif status == 404:
            msg = "Resource not found — check CONFLUENCE_URL and space/page identifiers."
        else:
            msg = str(e)
        raise RuntimeError(
            f"CONFLUENCE_HTTP_ERROR ({status}): {msg} Do not retry."
        ) from e
    except Exception as e:
        # Catches atlassian-python-api specific errors (ApiPermissionError, ApiError, etc.)
        msg = str(e)
        if "permission" in msg.lower() or "forbidden" in msg.lower():
            hint = "The API token lacks required Confluence permissions."
        elif "not found" in msg.lower():
            hint = "Resource not found — check space/page identifiers."
        elif "unauthorized" in msg.lower():
            hint = "Invalid credentials — check CONFLUENCE_USER and CONFLUENCE_API_TOKEN."
        else:
            hint = msg
        raise RuntimeError(
            f"CONFLUENCE_ERROR: {hint} Do not retry — inform the user."
        ) from e


def _markdown_to_storage(md: str) -> str:
    """Convert Markdown to Confluence Storage Format (HTML subset)."""
    return markdown2.markdown(md, extras=["fenced-code-blocks", "tables"])


def _get_section_html(page_body: str, heading: str) -> Optional[str]:
    """Extract HTML content of a section identified by its heading text."""
    soup = BeautifulSoup(page_body, "lxml")
    target = soup.find(["h1", "h2", "h3", "h4"], string=lambda t: t and heading.lower() in t.lower())
    if not target:
        return None
    parts = []
    for sibling in target.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in ("h1", "h2", "h3", "h4"):
            if sibling.name <= target.name:
                break
        parts.append(str(sibling))
    return "".join(parts).strip()


def _replace_section_html(page_body: str, heading: str, new_content_html: str) -> Optional[str]:
    """Replace the content of a section identified by heading. Returns new full body or None if not found."""
    soup = BeautifulSoup(page_body, "lxml")
    target = soup.find(["h1", "h2", "h3", "h4"], string=lambda t: t and heading.lower() in t.lower())
    if not target:
        return None

    # Remove all siblings that belong to this section
    to_remove = []
    for sibling in target.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in ("h1", "h2", "h3", "h4"):
            if sibling.name <= target.name:
                break
        to_remove.append(sibling)
    for el in to_remove:
        el.decompose()

    # Insert new content after the heading
    new_soup = BeautifulSoup(new_content_html, "lxml")
    for node in reversed(list(new_soup.body.children) if new_soup.body else []):
        target.insert_after(node.__copy__())

    return str(soup.body or soup)


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

class ConfluenceSearchInput(BaseModel):
    query: str = Field(description="Full-text search query")
    space_key: str = Field(default="", description="Optional Confluence space key to limit search (e.g. 'DEV')")
    limit: int = Field(default=10, description="Maximum number of results to return")


class ConfluenceSearchTool(LoggedTool):
    name: str = "ConfluenceSearch"
    description: str = (
        "Search Confluence pages by keywords. "
        "Returns a list of matching pages with their IDs, titles, and space keys. "
        "Use this to find the right page before reading or editing it."
    )
    args_schema: type[BaseModel] = ConfluenceSearchInput

    def _run(self, query: str, space_key: str = "", limit: int = 10) -> str:
        with _confluence_errors():
            client = _get_client()
            effective_space = space_key or settings.CONFLUENCE_SPACE_KEY or ""
            cql = f'text ~ "{query}" AND type = page'
            if effective_space:
                cql += f' AND space.key = "{effective_space}"'
            results = client.cql(cql, limit=limit).get("results", [])
            if not results:
                return "No pages found."
            lines = []
            for r in results:
                content = r.get("content", {})
                lines.append(
                    f"- ID: {content.get('id')} | Space: {content.get('space', {}).get('key')} | Title: {content.get('title')}"
                )
            return "\n".join(lines)


class ConfluenceGetPageInput(BaseModel):
    page_id: str = Field(default="", description="Confluence page ID (preferred)")
    title: str = Field(default="", description="Page title (used if page_id is not provided)")
    space_key: str = Field(default="", description="Space key — required when searching by title")


class ConfluenceGetPageTool(LoggedTool):
    name: str = "ConfluenceGetPage"
    description: str = (
        "Read the full content of a Confluence page. "
        "Provide page_id (fastest) or title+space_key. "
        "Returns the page content as plain text with headings preserved."
    )
    args_schema: type[BaseModel] = ConfluenceGetPageInput

    def _run(self, page_id: str = "", title: str = "", space_key: str = "") -> str:
        with _confluence_errors():
            client = _get_client()
            if page_id:
                page = client.get_page_by_id(page_id, expand="body.storage")
            elif title and space_key:
                page = client.get_page_by_title(space_key, title, expand="body.storage")
            else:
                return "Error: provide page_id or both title and space_key."
            if not page:
                return "Page not found."
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            soup = BeautifulSoup(body_html, "lxml")
            return f"Title: {page['title']}\nID: {page['id']}\n\n{soup.get_text(separator=chr(10))}"


class ConfluenceGetSectionInput(BaseModel):
    page_id: str = Field(description="Confluence page ID")
    heading: str = Field(description="Exact or partial heading text of the section to read")


class ConfluenceGetSectionTool(LoggedTool):
    name: str = "ConfluenceGetSection"
    description: str = (
        "Read only a specific section of a Confluence page by its heading. "
        "Much faster than reading the full page when you need one section. "
        "Returns the section content as plain text."
    )
    args_schema: type[BaseModel] = ConfluenceGetSectionInput

    def _run(self, page_id: str, heading: str) -> str:
        with _confluence_errors():
            client = _get_client()
            page = client.get_page_by_id(page_id, expand="body.storage")
            if not page:
                return "Page not found."
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            section_html = _get_section_html(body_html, heading)
            if section_html is None:
                return f"Section '{heading}' not found in page '{page['title']}'."
            soup = BeautifulSoup(section_html, "lxml")
            return soup.get_text(separator="\n")


# ---------------------------------------------------------------------------
# Write tools (only registered when CONFLUENCE_WRITE_ENABLED=true)
# ---------------------------------------------------------------------------

class ConfluenceCreatePageInput(BaseModel):
    #space_key: str = Field(description="Confluence space key where the page will be created (e.g. 'DEV')")
    title: str = Field(description="Title of the new page")
    content_markdown: str = Field(description="Page content in Markdown format")
    parent_id: str = Field(default="", description="Optional parent page ID to nest the new page under")


class ConfluenceCreatePageTool(LoggedTool):
    name: str = "ConfluenceCreatePage"
    description: str = (
        "Create a new Confluence page "
        "Write content in Markdown — it will be converted automatically. "
        "Optionally provide parent_id to nest it under an existing page."
    )
    args_schema: type[BaseModel] = ConfluenceCreatePageInput

    def _run(self, title: str, content_markdown: str, parent_id: str = "") -> str:
        with _confluence_errors():
            client = _get_client()
            effective_space = settings.CONFLUENCE_SPACE_KEY
            # if not effective_space:
            #     return "Error: space_key is required. Set CONFLUENCE_SPACE_KEY in config or pass space_key explicitly."
            body_html = _markdown_to_storage(content_markdown)
            kwargs = {"space": effective_space, "title": title, "body": body_html}
            if parent_id:
                kwargs["parent_id"] = parent_id
            result = client.create_page(**kwargs)
            page_id = result.get("id", "unknown")
            page_url = result.get("_links", {}).get("webui", "")
            return f"Page created. ID: {page_id}. URL: {settings.CONFLUENCE_URL}{page_url}"


class ConfluenceUpdateSectionInput(BaseModel):
    page_id: str = Field(description="Confluence page ID to update")
    heading: str = Field(description="Heading text of the section to replace")
    new_content_markdown: str = Field(description="New section content in Markdown (heading itself is NOT included)")


class ConfluenceUpdateSectionTool(LoggedTool):
    name: str = "ConfluenceUpdateSection"
    description: str = (
        "Replace the content of a specific section in a Confluence page. "
        "Only the section under the given heading is changed — the rest of the page is untouched. "
        "Write new content in Markdown format."
    )
    args_schema: type[BaseModel] = ConfluenceUpdateSectionInput

    def _run(self, page_id: str, heading: str, new_content_markdown: str) -> str:
        with _confluence_errors():
            client = _get_client()
            page = client.get_page_by_id(page_id, expand="body.storage,version")
            if not page:
                return "Page not found."
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            new_content_html = _markdown_to_storage(new_content_markdown)
            new_body = _replace_section_html(body_html, heading, new_content_html)
            if new_body is None:
                return f"Section '{heading}' not found. Use ConfluenceGetPage to check available headings."
            version = page["version"]["number"] + 1
            client.update_page(page_id=page_id, title=page["title"], body=new_body, version=version)
            return f"Section '{heading}' updated successfully in page '{page['title']}'."


class ConfluenceAppendSectionInput(BaseModel):
    page_id: str = Field(description="Confluence page ID")
    heading: str = Field(description="Heading text for the new section being appended")
    content_markdown: str = Field(description="Content of the new section in Markdown format")
    heading_level: int = Field(default=2, description="Heading level: 2 for H2, 3 for H3")


class ConfluenceAppendSectionTool(LoggedTool):
    name: str = "ConfluenceAppendSection"
    description: str = (
        "Append a new section to the end of an existing Confluence page. "
        "Provide the heading for the new section and its content in Markdown. "
        "Does not modify any existing content."
    )
    args_schema: type[BaseModel] = ConfluenceAppendSectionInput

    def _run(self, page_id: str, heading: str, content_markdown: str, heading_level: int = 2) -> str:
        with _confluence_errors():
            client = _get_client()
            page = client.get_page_by_id(page_id, expand="body.storage,version")
            if not page:
                return "Page not found."
            body_html = page.get("body", {}).get("storage", {}).get("value", "")
            new_section = f"<h{heading_level}>{heading}</h{heading_level}>\n{_markdown_to_storage(content_markdown)}"
            new_body = body_html + "\n" + new_section
            version = page["version"]["number"] + 1
            client.update_page(page_id=page_id, title=page["title"], body=new_body, version=version)
            return f"Section '{heading}' appended to page '{page['title']}'."


# ---------------------------------------------------------------------------
# Helper used by agents
# ---------------------------------------------------------------------------

def get_confluence_tools() -> list:
    """Return the appropriate set of Confluence tools based on config."""
    tools = [
        ConfluenceSearchTool(),
        ConfluenceGetPageTool(),
        ConfluenceGetSectionTool(),
    ]
    if settings.CONFLUENCE_WRITE_ENABLED:
        tools += [
            ConfluenceCreatePageTool(),
            ConfluenceUpdateSectionTool(),
            ConfluenceAppendSectionTool(),
        ]
    return tools
