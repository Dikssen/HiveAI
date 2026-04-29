"""
ReadLogsTool — reads service logs from sample_data/logs/.
Supports keyword search within log content.
"""
import os
from pydantic import BaseModel, Field

from app.tools.base import LoggedTool
from app.config import settings


class ReadLogsInput(BaseModel):
    query: str = Field(
        description="Keyword or phrase to search in logs. Use 'all' to get all logs."
    )
    log_file: str = Field(
        default="service.log",
        description="Log file name: 'service.log' or 'error.log'",
    )


class ReadLogsTool(LoggedTool):
    name: str = "ReadLogs"
    description: str = (
        "Read and search through service log files. "
        "Provide a keyword to search for or 'all' to get all logs. "
        "Available files: service.log, error.log"
    )
    args_schema: type[BaseModel] = ReadLogsInput

    def _run(self, query: str, log_file: str = "service.log") -> str:
        logs_dir = os.path.join(settings.SAMPLE_DATA_PATH, "logs")
        file_path = os.path.join(logs_dir, log_file)

        if not os.path.exists(file_path):
            return f"Log file '{log_file}' not found at {logs_dir}. Available: service.log, error.log"

        with open(file_path, "r") as f:
            lines = f.readlines()

        if query.lower() == "all":
            return "".join(lines[-100:])  # last 100 lines

        matched = [line for line in lines if query.lower() in line.lower()]

        if not matched:
            return f"No log entries found matching '{query}' in {log_file}."

        return f"Found {len(matched)} matching entries:\n" + "".join(matched[:50])
