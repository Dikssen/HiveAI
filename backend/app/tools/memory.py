"""
Chat memory tools — let agents read and search the current conversation history.
Each tool is bound to a chat_id at creation time via get_memory_tools().
"""
from pydantic import BaseModel, Field

from app.tools.base import LoggedTool


class GetChatHistoryInput(BaseModel):
    limit: int = Field(default=10, description="Number of recent messages to retrieve (max 20)")


class GetChatHistoryTool(LoggedTool):
    name: str = "GetChatHistory"
    description: str = (
        "Retrieve recent messages from the current conversation. "
        "Use when you need context about what was discussed earlier in this chat. "
        "Returns messages in chronological order with timestamps."
    )
    args_schema: type[BaseModel] = GetChatHistoryInput
    chat_id: int

    def _run(self, limit: int = 10) -> str:
        from app.db.session import SessionLocal
        from app.models.message import Message

        db = SessionLocal()
        try:
            limit = min(limit, 20)
            messages = (
                db.query(Message)
                .filter(Message.chat_id == self.chat_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )
            messages = list(reversed(messages))
            if not messages:
                return "No conversation history found."
            lines = [f"Last {len(messages)} message(s) from this conversation:"]
            for msg in messages:
                ts = str(msg.created_at)[:16]
                lines.append(f"\n[{ts}] {msg.role.upper()}:\n{msg.content}")
            return "\n".join(lines)
        finally:
            db.close()


class SearchChatHistoryInput(BaseModel):
    query: str = Field(description="Keyword or phrase to search in the conversation history")


class SearchChatHistoryTool(LoggedTool):
    name: str = "SearchChatHistory"
    description: str = (
        "Search the current conversation history for specific topics or keywords. "
        "Use when you need to find what was discussed about a specific subject earlier in this chat."
    )
    args_schema: type[BaseModel] = SearchChatHistoryInput
    chat_id: int

    def _run(self, query: str) -> str:
        from app.db.session import SessionLocal
        from app.models.message import Message

        db = SessionLocal()
        try:
            messages = (
                db.query(Message)
                .filter(
                    Message.chat_id == self.chat_id,
                    Message.content.ilike(f"%{query}%"),
                )
                .order_by(Message.created_at.desc())
                .limit(5)
                .all()
            )
            if not messages:
                return f"No messages found containing '{query}'."
            lines = [f"Found {len(messages)} message(s) containing '{query}':"]
            for msg in reversed(messages):
                ts = str(msg.created_at)[:16]
                lines.append(f"\n[{ts}] {msg.role.upper()}:\n{msg.content}")
            return "\n".join(lines)
        finally:
            db.close()


def get_memory_tools(chat_id: int) -> list:
    return [
        GetChatHistoryTool(chat_id=chat_id),
        SearchChatHistoryTool(chat_id=chat_id),
    ]
