"""
Knowledge base tools — agents search and read knowledge entries.
Each tool is bound to an agent_name at creation time.
Searches return the agent's own entries + global entries (agent_name IS NULL).
Entries are managed via /api/knowledge.
"""
from typing import Optional
from pydantic import BaseModel, Field

from app.tools.base import LoggedTool


class KnowledgeSearchInput(BaseModel):
    query: str = Field(
        description=(
            "Search query to find relevant knowledge entries. "
            "Searches in title, tags, and content. "
            "Examples: 'fleio database', 'server infrastructure', 'client billing'"
        )
    )


class KnowledgeSearchTool(LoggedTool):
    name: str = "KnowledgeSearch"
    description: str = (
        "Search the internal knowledge base for infrastructure facts, schema docs, runbooks, and known patterns. "
        "Use this when you need context about the system — database structure, server setup, common issues, etc. "
        "Returns matching entry titles and a short preview. Use KnowledgeGet to read the full content."
    )
    args_schema: type[BaseModel] = KnowledgeSearchInput
    agent_name: Optional[str] = None

    def _run(self, query: str) -> str:
        from app.db.session import SessionLocal
        from app.models.knowledge_entry import KnowledgeEntry
        from sqlalchemy import or_

        db = SessionLocal()
        try:
            q = f"%{query.lower()}%"
            base = db.query(KnowledgeEntry).filter(
                KnowledgeEntry.title.ilike(q)
                | KnowledgeEntry.tags.ilike(q)
                | KnowledgeEntry.content.ilike(q)
            )
            # own entries + global
            if self.agent_name:
                base = base.filter(
                    or_(
                        KnowledgeEntry.agent_name == self.agent_name,
                        KnowledgeEntry.agent_name.is_(None),
                    )
                )
            entries = base.order_by(KnowledgeEntry.updated_at.desc()).limit(10).all()

            if not entries:
                return f"No knowledge entries found for '{query}'."
            lines = [f"Found {len(entries)} entry(ies) for '{query}':"]
            for e in entries:
                tags = f" [{e.tags}]" if e.tags else ""
                scope = f" (private: {e.agent_name})" if e.agent_name else " (global)"
                preview = e.content[:120].replace("\n", " ").strip()
                lines.append(f"\n[{e.id}] {e.title}{tags}{scope}\n  {preview}...")
            return "\n".join(lines)
        finally:
            db.close()


class KnowledgeGetInput(BaseModel):
    title: str = Field(description="Exact title of the knowledge entry to read. Use KnowledgeSearch to find titles.")


class KnowledgeGetTool(LoggedTool):
    name: str = "KnowledgeGet"
    description: str = (
        "Read the full content of a knowledge base entry by its exact title. "
        "Use KnowledgeSearch first to find the correct title. "
        "Returns the complete markdown content of the entry."
    )
    args_schema: type[BaseModel] = KnowledgeGetInput
    agent_name: Optional[str] = None

    def _run(self, title: str) -> str:
        from app.db.session import SessionLocal
        from app.models.knowledge_entry import KnowledgeEntry
        from sqlalchemy import or_

        db = SessionLocal()
        try:
            base = db.query(KnowledgeEntry).filter(KnowledgeEntry.title.ilike(title))
            if self.agent_name:
                base = base.filter(
                    or_(
                        KnowledgeEntry.agent_name == self.agent_name,
                        KnowledgeEntry.agent_name.is_(None),
                    )
                )
            entry = base.first()
            if not entry:
                return f"Knowledge entry '{title}' not found. Use KnowledgeSearch to find available entries."
            tags = f"\nTags: {entry.tags}" if entry.tags else ""
            scope = f"\nScope: private ({entry.agent_name})" if entry.agent_name else "\nScope: global"
            updated = str(entry.updated_at)[:16] if entry.updated_at else ""
            return f"# {entry.title}{tags}{scope}\nUpdated: {updated}\n\n{entry.content}"
        finally:
            db.close()


class KnowledgeSaveInput(BaseModel):
    title: str = Field(description="Short descriptive title for this knowledge entry, e.g. 'Fleio DB Schema', 'Server X config'")
    content: str = Field(description="Full content in markdown format. Be precise and factual — no assumptions.")
    reason: str = Field(
        description=(
            "Why is this worth saving permanently? "
            "Must be one of: 'discovered infrastructure fact', 'recurring issue pattern', "
            "'schema or config that will be needed again', 'verified fix or workaround'. "
            "Do NOT save: task progress, temporary findings, or anything specific to this one request."
        )
    )
    tags: str = Field(default="", description="Comma-separated tags, e.g. 'fleio,database,mysql'")
    scope: str = Field(
        default="private",
        description="'private' to save only for yourself, 'global' to share with all agents."
    )


class KnowledgeSaveTool(LoggedTool):
    name: str = "KnowledgeSave"
    description: str = (
        "Save a permanent knowledge entry to the shared knowledge base. "
        "Use ONLY for facts that will be useful in FUTURE sessions: "
        "infrastructure schemas, server configs, recurring issue patterns, verified fixes. "
        "Do NOT use for: current task progress, one-off findings, temporary context, or assumptions. "
        "If an entry with this title already exists — it will be fully replaced."
    )
    args_schema: type[BaseModel] = KnowledgeSaveInput
    agent_name: Optional[str] = None

    def _run(self, title: str, content: str, reason: str, tags: str = "", scope: str = "private") -> str:
        from datetime import datetime, timezone
        from app.db.session import SessionLocal
        from app.models.knowledge_entry import KnowledgeEntry

        agent_name = self.agent_name if scope == "private" else None

        db = SessionLocal()
        try:
            existing = db.query(KnowledgeEntry).filter(
                KnowledgeEntry.title == title,
                KnowledgeEntry.agent_name == agent_name,
            ).first()

            if existing:
                existing.content = content
                existing.tags = tags or existing.tags
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                return f"Knowledge entry '{title}' updated ({scope}). Reason: {reason}"
            else:
                entry = KnowledgeEntry(
                    title=title,
                    content=content,
                    tags=tags or None,
                    agent_name=agent_name,
                )
                db.add(entry)
                db.commit()
                return f"Knowledge entry '{title}' saved ({scope}). Reason: {reason}"
        finally:
            db.close()


class KnowledgeAppendInput(BaseModel):
    title: str = Field(description="Exact title of an existing knowledge entry to append to.")
    content: str = Field(description="New content to append in markdown. Will be added at the end with a separator.")
    reason: str = Field(
        description=(
            "Why is this addition worth saving permanently? "
            "Must be a new verified fact, a new pattern, or an update to existing info. "
            "Do NOT append temporary findings or task-specific context."
        )
    )


class KnowledgeAppendTool(LoggedTool):
    name: str = "KnowledgeAppend"
    description: str = (
        "Append new content to an existing knowledge entry without replacing it. "
        "Use when you have a new verified fact that extends existing knowledge — "
        "for example, a new server added to an existing infrastructure doc, or a new known issue pattern. "
        "The entry must already exist — use KnowledgeSave to create a new one."
    )
    args_schema: type[BaseModel] = KnowledgeAppendInput
    agent_name: Optional[str] = None

    def _run(self, title: str, content: str, reason: str) -> str:
        from datetime import datetime, timezone
        from app.db.session import SessionLocal
        from app.models.knowledge_entry import KnowledgeEntry
        from sqlalchemy import or_

        db = SessionLocal()
        try:
            base = db.query(KnowledgeEntry).filter(KnowledgeEntry.title == title)
            if self.agent_name:
                base = base.filter(
                    or_(
                        KnowledgeEntry.agent_name == self.agent_name,
                        KnowledgeEntry.agent_name.is_(None),
                    )
                )
            entry = base.first()

            if not entry:
                return (
                    f"Entry '{title}' not found. Use KnowledgeSearch to find existing entries "
                    f"or KnowledgeSave to create a new one."
                )

            now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            entry.content = entry.content.rstrip() + f"\n\n---\n*Appended {now}*\n\n{content}"
            entry.updated_at = datetime.now(timezone.utc)
            db.commit()
            return f"Appended to '{title}'. Reason: {reason}"
        finally:
            db.close()


def get_knowledge_tools(agent_name: Optional[str] = None) -> list:
    return [
        KnowledgeSearchTool(agent_name=agent_name),
        KnowledgeGetTool(agent_name=agent_name),
        KnowledgeSaveTool(agent_name=agent_name),
        KnowledgeAppendTool(agent_name=agent_name),
    ]
