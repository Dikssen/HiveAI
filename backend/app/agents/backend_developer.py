from app.agents.base import BaseITAgent
from app.tools.read_logs import ReadLogsTool
from app.tools.code_review import CodeReviewTool
from app.tools.report_writer import ReportWriterTool
from app.tools.git_serch import ListRepositoriesTool
from app.tools.local_repo import (
    CloneOrUpdateRepoTool, ListBranchesTool, SwitchBranchTool,
    ListLocalFilesTool, ReadLocalFileTool, WriteLocalFileTool,
)

class BackendDeveloperAgent(BaseITAgent):
    name = "BackendDeveloperAgent"
    role = "Senior Backend Developer"
    goal = (
        "Analyze backend issues, read error logs, identify root causes, and fix code. "
        "Workflow: clone repo → list files → read relevant files → implement fix → "
        "save EVERY changed file using WriteLocalFile (confirmation 'Written X bytes to' must appear). "
        "Never just describe changes in text — always write them to disk."
    )
    backstory = (
        "You are a Senior Backend Developer with deep expertise in Python, FastAPI, "
        "databases, and distributed systems. You read logs like a book, "
        "spot bugs quickly, always explain the root cause before touching code, "
        "and always save your changes to disk so others can review them."
    )
    description = "Analyzes errors, reads logs, clones repos, reads and writes code files, proposes and applies fixes."
    capabilities = [
        "error log analysis",
        "root cause identification",
        "code review",
        "bug fixing and code improvement",
        "backend architecture review",
        "API debugging",
        "list all GitHub repositories",
        "clone or update a GitHub repository locally",
        "list branches of a repository",
        "switch between branches",
        "list files in a local repository",
        "read file contents from a local repository",
        "write or overwrite files in a local repository (WriteLocalFile)",
    ]

    def get_tools(self):
        return [
            ReadLogsTool(), CodeReviewTool(), ReportWriterTool(),
            ListRepositoriesTool(),
            CloneOrUpdateRepoTool(), ListBranchesTool(), SwitchBranchTool(),
            ListLocalFilesTool(), ReadLocalFileTool(), WriteLocalFileTool(),
        ]
