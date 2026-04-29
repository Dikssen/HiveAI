from app.tools.base import LoggedTool
from github import Github, Auth
from app.db.integration_config_helper import get_integration_value


class ListRepositoriesTool(LoggedTool):
    name: str = "ListRepositories"
    description: str = (
        "Returns a list of all GitHub repositories with their names and descriptions. "
        "Use this to find the correct repository name before cloning it with CloneOrUpdateRepo."
    )

    def _run(self) -> str:
        auth = Auth.Token(get_integration_value("GITHUB_TOKEN"))
        git = Github(auth=auth)

        repos = git.get_user().get_repos()
        lines = []
        for repo in repos:
            desc = repo.description or "no description"
            lines.append(f"- {repo.name}: {desc}")
        return "\n".join(lines)
