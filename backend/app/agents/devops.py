from app.agents.base import BaseITAgent
from app.tools.read_logs import ReadLogsTool
from app.tools.docker_inspect import DockerInspectTool
from app.tools.report_writer import ReportWriterTool
from app.tools.git_serch import ListRepositoriesTool
from app.tools.local_repo import (
    CloneOrUpdateRepoTool, ListBranchesTool, SwitchBranchTool,
    ListLocalFilesTool, ReadLocalFileTool,
)

class DevOpsAgent(BaseITAgent):
    name = "DevOpsAgent"
    role = "DevOps Engineer"
    goal = (
        "Analyze infrastructure issues, review Docker and CI/CD configurations, "
        "investigate service crashes, check environment variables, "
        "and propose deployment and stability improvements."
    )
    backstory = (
        "You are a DevOps Engineer who keeps services running. "
        "You know Docker, Kubernetes, CI/CD pipelines, and cloud infrastructure inside out. "
        "You look at logs, configs, and metrics to find the root cause of outages and "
        "prevent them from happening again."
    )
    description = "Analyzes Docker, CI/CD, logs, env vars, and GitHub repositories. Proposes infrastructure and deployment fixes."
    capabilities = [
        "Docker configuration review",
        "CI/CD pipeline analysis",
        "environment variable auditing",
        "service crash analysis",
        "infrastructure improvement proposals",
        "deployment strategy advice",
        "list all GitHub repositories with descriptions",
        "clone or update a GitHub repository locally",
        "list branches of a repository",
        "switch between branches",
        "list files in a local repository",
        "read file contents from a local repository",
    ]

    def get_tools(self):
        return [
            ReadLogsTool(), DockerInspectTool(), ReportWriterTool(),
            ListRepositoriesTool(),
            CloneOrUpdateRepoTool(), ListBranchesTool(), SwitchBranchTool(),
            ListLocalFilesTool(), ReadLocalFileTool(),
        ]
