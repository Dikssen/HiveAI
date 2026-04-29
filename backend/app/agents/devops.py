from app.agents.base import BaseITAgent
from app.tools.read_logs import ReadLogsTool
from app.tools.docker_inspect import DockerInspectTool
from app.tools.report_writer import ReportWriterTool
from app.tools.git_serch import ListRepositoriesTool
from app.tools.local_repo import (
    CloneOrUpdateRepoTool, ListBranchesTool, SwitchBranchTool,
    ListLocalFilesTool, ReadLocalFileTool, WriteLocalFileTool,
)

class DevOpsAgent(BaseITAgent):
    name = "DevOpsAgent"
    role = "DevOps Engineer"
    goal = (
        "Analyze infrastructure issues, review Docker and CI/CD configurations, "
        "investigate service crashes, and apply fixes to config files. "
        "Workflow: read logs/configs → identify root cause → fix config files using WriteLocalFile "
        "(confirmation 'Written X bytes to' must appear) → document what was changed and why."
    )
    backstory = (
        "You are a DevOps Engineer who keeps services running 24/7. "
        "You know Docker, Kubernetes, CI/CD pipelines, and cloud infrastructure inside out. "
        "You look at logs, configs, and container state to find the root cause of outages, "
        "fix them directly in config files, and prevent recurrence."
    )
    description = "Analyzes Docker/CI/CD configs, logs, env vars, repos. Applies infrastructure fixes to local config files."
    capabilities = [
        "Docker configuration review and fixing",
        "CI/CD pipeline analysis",
        "environment variable auditing",
        "service crash root cause analysis",
        "infrastructure improvement proposals",
        "deployment strategy advice",
        "list all GitHub repositories with descriptions",
        "clone or update a GitHub repository locally",
        "list branches of a repository",
        "switch between branches",
        "list files in a local repository",
        "read file contents from a local repository",
        "write or overwrite config files in a local repository (WriteLocalFile)",
    ]

    def get_tools(self):
        return [
            ReadLogsTool(), DockerInspectTool(), ReportWriterTool(),
            ListRepositoriesTool(),
            CloneOrUpdateRepoTool(), ListBranchesTool(), SwitchBranchTool(),
            ListLocalFilesTool(), ReadLocalFileTool(), WriteLocalFileTool(),
        ]
