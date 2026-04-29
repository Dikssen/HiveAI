"""
Jira tools — search, read, and manage Jira issues.
Write tools (CreateIssue, AddComment, TransitionIssue, UpdateIssue) are only registered
when JIRA_WRITE_ENABLED=true in integration config.
"""
from contextlib import contextmanager
from typing import Optional

import requests
from atlassian import Jira
from pydantic import BaseModel, Field

from app.db.integration_config_helper import get_integration_value
from app.tools.base import LoggedTool

_NOT_CONFIGURED_MSG = (
    "JIRA_NOT_CONFIGURED: Jira integration is not available. "
    "Configure JIRA_URL, JIRA_USER, and JIRA_API_TOKEN via /api/integrations. "
    "Do not retry — inform the user that Jira must be configured first."
)


def _get_client() -> Jira:
    url = get_integration_value("JIRA_URL") or ""
    user = get_integration_value("JIRA_USER") or ""
    token = get_integration_value("JIRA_API_TOKEN") or ""

    if not url or not user or not token:
        raise RuntimeError(_NOT_CONFIGURED_MSG)

    return Jira(url=url, username=user, password=token, cloud=True)


@contextmanager
def _jira_errors():
    try:
        yield
    except RuntimeError:
        raise
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            f"JIRA_UNREACHABLE: Cannot connect to Jira ({e}). "
            "Check JIRA_URL and network access. Do not retry."
        ) from e
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        if status == 401:
            msg = "Invalid credentials — check JIRA_USER and JIRA_API_TOKEN."
        elif status == 403:
            msg = "Access denied — the API token may lack required permissions."
        elif status == 404:
            msg = "404 Not Found — issue or project does not exist."
        else:
            msg = str(e)
        raise RuntimeError(f"JIRA_HTTP_ERROR ({status}): {msg} Do not retry.") from e
    except Exception as e:
        msg = str(e)
        if "no content" in msg.lower() or ("not found" in msg.lower() and "permission" not in msg.lower()):
            raise RuntimeError(
                f"JIRA_NOT_FOUND: 404 Not Found — {msg} Do not retry — inform the user."
            ) from e
        elif "permission" in msg.lower() or "forbidden" in msg.lower():
            hint = "The API token lacks required Jira permissions."
        elif "unauthorized" in msg.lower():
            hint = "Invalid credentials — check JIRA_USER and JIRA_API_TOKEN."
        else:
            hint = msg
        raise RuntimeError(f"JIRA_ERROR: {hint} Do not retry — inform the user.") from e


def _format_issue_short(issue: dict) -> str:
    key = issue.get("key", "?")
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    status = (fields.get("status") or {}).get("name", "")
    assignee = ((fields.get("assignee") or {}).get("displayName") or "Unassigned")
    priority = (fields.get("priority") or {}).get("name", "")
    itype = (fields.get("issuetype") or {}).get("name", "")
    return f"[{key}] {summary} | {itype} | {priority} | {status} | {assignee}"


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

class JiraSearchIssuesInput(BaseModel):
    jql: str = Field(
        description=(
            "JQL query string. Examples: "
            "'project = DEV AND status = \"In Progress\"', "
            "'assignee = currentUser() AND sprint in openSprints()', "
            "'text ~ \"login bug\" AND type = Bug ORDER BY created DESC'"
        )
    )
    limit: int = Field(default=20, description="Maximum number of results to return (max 50)")


class JiraSearchIssuesTool(LoggedTool):
    name: str = "JiraSearchIssues"
    description: str = (
        "Search Jira issues using JQL (Jira Query Language). "
        "Use this to find issues by project, status, assignee, type, text, sprint, etc. "
        "Returns a list of matching issues with key, summary, type, priority, status, and assignee. "
        "Use JiraGetIssue to read full details of a specific issue."
    )
    args_schema: type[BaseModel] = JiraSearchIssuesInput

    def _run(self, jql: str, limit: int = 20) -> str:
        with _jira_errors():
            client = _get_client()
            result = client.jql(jql, limit=min(limit, 50))
            issues = result.get("issues", [])
            if not issues:
                return "No issues found."
            lines = [f"Found {len(issues)} issue(s):"]
            for issue in issues:
                lines.append(_format_issue_short(issue))
            return "\n".join(lines)


class JiraGetIssueInput(BaseModel):
    issue_key: str = Field(description="Jira issue key, e.g. 'PROJ-123'")


class JiraGetIssueTool(LoggedTool):
    name: str = "JiraGetIssue"
    description: str = (
        "Get full details of a Jira issue by its key (e.g. PROJ-123). "
        "Returns summary, description, type, priority, status, assignee, reporter, "
        "labels, and the last 5 comments. "
        "Use JiraSearchIssues first if you don't know the issue key."
    )
    args_schema: type[BaseModel] = JiraGetIssueInput

    def _run(self, issue_key: str) -> str:
        with _jira_errors():
            client = _get_client()
            issue = client.issue(issue_key)
            if not issue:
                return f"Issue '{issue_key}' not found."
            fields = issue.get("fields", {})

            summary = fields.get("summary", "")
            description = fields.get("description") or "(no description)"
            status = (fields.get("status") or {}).get("name", "")
            itype = (fields.get("issuetype") or {}).get("name", "")
            priority = (fields.get("priority") or {}).get("name", "")
            assignee = ((fields.get("assignee") or {}).get("displayName") or "Unassigned")
            reporter = ((fields.get("reporter") or {}).get("displayName") or "Unknown")
            labels = ", ".join(fields.get("labels") or []) or "none"
            created = (fields.get("created") or "")[:10]
            updated = (fields.get("updated") or "")[:10]

            comments_data = (fields.get("comment") or {}).get("comments", [])
            comments_text = ""
            if comments_data:
                last_5 = comments_data[-5:]
                comment_lines = []
                for c in last_5:
                    author = (c.get("author") or {}).get("displayName", "?")
                    body = c.get("body", "")
                    comment_lines.append(f"  [{author}]: {body}")
                comments_text = "\nComments (last 5):\n" + "\n".join(comment_lines)

            return (
                f"Key: {issue_key}\n"
                f"Summary: {summary}\n"
                f"Type: {itype} | Priority: {priority} | Status: {status}\n"
                f"Assignee: {assignee} | Reporter: {reporter}\n"
                f"Labels: {labels}\n"
                f"Created: {created} | Updated: {updated}\n"
                f"Description:\n{description}"
                f"{comments_text}"
            )


class JiraGetProjectIssuesInput(BaseModel):
    project_key: str = Field(
        default="",
        description="Jira project key, e.g. 'DEV'. Leave empty to use the default configured project key."
    )
    status: str = Field(
        default="",
        description="Filter by status name, e.g. 'To Do', 'In Progress', 'Done'. Empty returns all statuses."
    )
    limit: int = Field(default=30, description="Maximum number of issues to return")


class JiraGetProjectIssuesTool(LoggedTool):
    name: str = "JiraGetProjectIssues"
    description: str = (
        "List issues in a Jira project. Optionally filter by status. "
        "Returns a concise list with key, summary, type, priority, status, and assignee. "
        "Use this to get an overview of a project's backlog or active sprint."
    )
    args_schema: type[BaseModel] = JiraGetProjectIssuesInput

    def _run(self, project_key: str = "", status: str = "", limit: int = 30) -> str:
        with _jira_errors():
            client = _get_client()
            key = project_key or get_integration_value("JIRA_PROJECT_KEY") or ""
            if not key:
                return "Error: provide project_key or set JIRA_PROJECT_KEY via /api/integrations."
            jql = f'project = "{key}"'
            if status:
                jql += f' AND status = "{status}"'
            jql += " ORDER BY updated DESC"
            result = client.jql(jql, limit=min(limit, 50))
            issues = result.get("issues", [])
            if not issues:
                return f"No issues found in project '{key}'" + (f" with status '{status}'" if status else "") + "."
            lines = [f"Project {key} — {len(issues)} issue(s):"]
            for issue in issues:
                lines.append(_format_issue_short(issue))
            return "\n".join(lines)


# ---------------------------------------------------------------------------
# Write tools (only registered when JIRA_WRITE_ENABLED=true)
# ---------------------------------------------------------------------------

class JiraCreateIssueInput(BaseModel):
    summary: str = Field(description="Issue title / summary")
    description: str = Field(default="", description="Detailed description of the issue")
    issue_type: str = Field(
        default="Task",
        description="Issue type: 'Bug', 'Task', 'Story', 'Epic', 'Sub-task'"
    )
    priority: str = Field(
        default="Medium",
        description="Priority: 'Highest', 'High', 'Medium', 'Low', 'Lowest'"
    )
    project_key: str = Field(
        default="",
        description="Jira project key, e.g. 'DEV'. Leave empty to use the default configured project."
    )
    assignee_account_id: str = Field(
        default="",
        description="Assignee account ID (optional). Leave empty to leave unassigned."
    )
    labels: str = Field(
        default="",
        description="Comma-separated labels to add, e.g. 'backend,api'. Leave empty for no labels."
    )


class JiraCreateIssueTool(LoggedTool):
    name: str = "JiraCreateIssue"
    description: str = (
        "Create a new Jira issue. "
        "Use for creating tasks, bug reports, stories, or epics. "
        "Returns the created issue key and URL."
    )
    args_schema: type[BaseModel] = JiraCreateIssueInput

    def _run(
        self,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        priority: str = "Medium",
        project_key: str = "",
        assignee_account_id: str = "",
        labels: str = "",
    ) -> str:
        with _jira_errors():
            client = _get_client()
            key = project_key or get_integration_value("JIRA_PROJECT_KEY") or ""
            if not key:
                return "Error: provide project_key or set JIRA_PROJECT_KEY via /api/integrations."

            fields: dict = {
                "project": {"key": key},
                "summary": summary,
                "issuetype": {"name": issue_type},
                "priority": {"name": priority},
            }
            if description:
                fields["description"] = description
            if assignee_account_id:
                fields["assignee"] = {"accountId": assignee_account_id}
            if labels:
                fields["labels"] = [l.strip() for l in labels.split(",") if l.strip()]

            result = client.create_issue(fields=fields)
            issue_key = result.get("key", "unknown")
            base_url = get_integration_value("JIRA_URL") or ""
            url = f"{base_url.rstrip('/')}/browse/{issue_key}"
            return f"Issue created: {issue_key}\nURL: {url}"


class JiraAddCommentInput(BaseModel):
    issue_key: str = Field(description="Jira issue key, e.g. 'PROJ-123'")
    comment: str = Field(description="Comment text to add to the issue")


class JiraAddCommentTool(LoggedTool):
    name: str = "JiraAddComment"
    description: str = (
        "Add a comment to an existing Jira issue. "
        "Use to document findings, progress updates, or questions on a ticket."
    )
    args_schema: type[BaseModel] = JiraAddCommentInput

    def _run(self, issue_key: str, comment: str) -> str:
        with _jira_errors():
            client = _get_client()
            client.add_comment(issue_key, comment)
            return f"Comment added to {issue_key}."


class JiraTransitionIssueInput(BaseModel):
    issue_key: str = Field(description="Jira issue key, e.g. 'PROJ-123'")
    status: str = Field(
        description=(
            "Target status name, e.g. 'To Do', 'In Progress', 'In Review', 'Done'. "
            "Must match an available transition for this issue."
        )
    )


class JiraTransitionIssueTool(LoggedTool):
    name: str = "JiraTransitionIssue"
    description: str = (
        "Move a Jira issue to a different status (e.g. from 'To Do' to 'In Progress'). "
        "Use JiraGetIssue first to check the current status. "
        "Fails if the target status is not a valid transition from the current state."
    )
    args_schema: type[BaseModel] = JiraTransitionIssueInput

    def _run(self, issue_key: str, status: str) -> str:
        with _jira_errors():
            client = _get_client()
            transitions = client.get_issue_transitions(issue_key)
            available = [t.get("name", "") for t in transitions]
            match = next((t for t in transitions if t.get("name", "").lower() == status.lower()), None)
            if not match:
                return (
                    f"Transition to '{status}' is not available for {issue_key}. "
                    f"Available transitions: {', '.join(available)}"
                )
            client.set_issue_status(issue_key, status)
            return f"Issue {issue_key} transitioned to '{status}'."


class JiraUpdateIssueInput(BaseModel):
    issue_key: str = Field(description="Jira issue key, e.g. 'PROJ-123'")
    summary: str = Field(default="", description="New summary/title. Leave empty to keep current.")
    description: str = Field(default="", description="New description. Leave empty to keep current.")
    priority: str = Field(
        default="",
        description="New priority: 'Highest', 'High', 'Medium', 'Low', 'Lowest'. Leave empty to keep current."
    )
    assignee_account_id: str = Field(
        default="",
        description="New assignee account ID. Leave empty to keep current."
    )


class JiraUpdateIssueTool(LoggedTool):
    name: str = "JiraUpdateIssue"
    description: str = (
        "Update fields of an existing Jira issue (summary, description, priority, assignee). "
        "Only fields with non-empty values are updated — others are left unchanged. "
        "Use JiraTransitionIssue to change the status."
    )
    args_schema: type[BaseModel] = JiraUpdateIssueInput

    def _run(
        self,
        issue_key: str,
        summary: str = "",
        description: str = "",
        priority: str = "",
        assignee_account_id: str = "",
    ) -> str:
        with _jira_errors():
            client = _get_client()
            fields: dict = {}
            if summary:
                fields["summary"] = summary
            if description:
                fields["description"] = description
            if priority:
                fields["priority"] = {"name": priority}
            if assignee_account_id:
                fields["assignee"] = {"accountId": assignee_account_id}
            if not fields:
                return "Nothing to update — all fields are empty."
            client.update_issue_field(issue_key, fields)
            updated = ", ".join(fields.keys())
            return f"Issue {issue_key} updated: {updated}."


# ---------------------------------------------------------------------------
# Helper used by agents
# ---------------------------------------------------------------------------

def get_jira_tools() -> list:
    """Return the appropriate set of Jira tools based on integration config."""
    tools: list = [
        JiraSearchIssuesTool(),
        JiraGetIssueTool(),
        JiraGetProjectIssuesTool(),
    ]
    write_enabled = str(get_integration_value("JIRA_WRITE_ENABLED", fallback="false")).lower() in ("true", "1", "yes")
    if write_enabled:
        tools += [
            JiraCreateIssueTool(),
            JiraAddCommentTool(),
            JiraTransitionIssueTool(),
            JiraUpdateIssueTool(),
        ]
    return tools
