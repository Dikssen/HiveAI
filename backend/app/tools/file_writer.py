import os
import uuid
from pathlib import Path

import structlog
from pydantic import BaseModel, Field

from app.config import settings
from app.tools.base import LoggedTool

logger = structlog.get_logger()

ALLOWED_EXTENSIONS = {
    ".html", ".htm", ".css", ".js",
    ".py", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml",
    ".csv", ".txt", ".md", ".sql",
    ".sh", ".dockerfile",
}


class FileWriterInput(BaseModel):
    filename: str = Field(description="File name with extension, e.g. 'report.html', 'script.py'")
    content: str = Field(description="Full file content as a string")


class FileWriterTool(LoggedTool):
    name: str = "FileWriter"
    description: str = (
        "Save generated content as a downloadable file. "
        "Use when the user asks to generate a file (HTML page, CSV, script, etc.). "
        "Returns a download URL to include in your response."
    )
    args_schema: type = FileWriterInput

    def _run(self, filename: str, content: str) -> str:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            return f"[TOOL_ERROR] Extension '{ext}' is not allowed. Supported: {', '.join(sorted(ALLOWED_EXTENSIONS))}"

        files_dir = Path(settings.FILES_DIR)
        files_dir.mkdir(parents=True, exist_ok=True)

        # Prefix with UUID to avoid collisions
        unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
        file_path = files_dir / unique_name

        file_path.write_text(content, encoding="utf-8")
        logger.info("file_written", filename=unique_name, bytes=len(content.encode()))

        download_url = f"/api/files/{unique_name}"
        return (
            f"File saved successfully.\n"
            f"Download: [{filename}]({download_url})\n\n"
            f"Share this link with the user so they can download the file."
        )
