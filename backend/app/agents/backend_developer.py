from app.agents.base import BaseITAgent
from app.tools.read_logs import ReadLogsTool
from app.tools.code_review import CodeReviewTool
from app.tools.report_writer import ReportWriterTool
from app.tools.git_serch import ListRepositoriesTool
from app.tools.local_repo import (
    CloneOrUpdateRepoTool, ListBranchesTool, SwitchBranchTool,
    ListLocalFilesTool, ReadLocalFileTool, WriteLocalFileTool,
)
from app.tools.code_edit import (
    CodeReadRangeTool, CodeReadSymbolTool,
    CodeReplaceRangeTool, CodeReplaceSymbolTool, CodeInsertAtLineTool,
)
from app.tools.confluence import get_confluence_tools

class BackendDeveloperAgent(BaseITAgent):
    name = "BackendDeveloperAgent"
    role = "Senior Backend Developer"
    goal = (
        "Analyze backend issues, read error logs, identify root causes, and fix code. "
        "Workflow: clone repo → list files → read relevant files → implement fix using block editing tools."
    )
    backstory = (
        "You are a Senior Backend Developer with deep expertise in Python, FastAPI, "
        "databases, and distributed systems. You read logs like a book, "
        "spot bugs quickly, and always explain the root cause before touching code."
    )
    description = "Analyzes errors, reads logs, clones repos, reads and edits code files, proposes and applies fixes."
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
        "edit specific functions, classes, or line ranges in code files",
    ]

    def get_tools(self):
        return [
            ReadLogsTool(), CodeReviewTool(), ReportWriterTool(),
            ListRepositoriesTool(),
            CloneOrUpdateRepoTool(), ListBranchesTool(), SwitchBranchTool(),
            ListLocalFilesTool(), ReadLocalFileTool(), WriteLocalFileTool(),
            CodeReadRangeTool(), CodeReadSymbolTool(),
            CodeReplaceRangeTool(), CodeReplaceSymbolTool(), CodeInsertAtLineTool(),
            *get_confluence_tools(),
        ]
