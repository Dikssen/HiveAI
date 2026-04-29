from pydantic import BaseModel, Field
from app.tools.base import LoggedTool
from github import Github, Auth
from app.config import settings


class ListRepositoriesTool(LoggedTool):
    name: str = "ListRepositories"
    description: str = (
        "Use this tool to get a full list of all company GitHub repositories "
        "with their names and descriptions. "
        "Call this first before searching in a specific repository."
    )

    def _run(self) -> str:
        auth = Auth.Token(settings.GITHUB_TOKEN)
        git = Github(auth=auth)

        repos = git.get_user().get_repos()
        lines = []
        for repo in repos:
            desc = repo.description or "no description"
            lines.append(f"- {repo.name}: {desc}")
        return "\n".join(lines)


class SearchInRepositoryInput(BaseModel):
    repo_name: str = Field(description="Exact repository name, e.g. 'auth-service'")
    query: str = Field(description="Keyword, function name, or code snippet to search for")


class SearchInRepositoryTool(LoggedTool):
    name: str = "SearchInRepository"
    description: str = (
        "Search for code, files, or keywords inside a specific GitHub repository. "
        "Use ListRepositories first to get the correct repository name."
    )
    args_schema: type[BaseModel] = SearchInRepositoryInput

    def _run(self, repo_name: str, query: str) -> str:
        auth = Auth.Token(settings.GITHUB_TOKEN)
        git = Github(auth=auth)

        repo = git.get_user().get_repo(repo_name)
        results = repo.search_code(query)  # GitHub code search within repo
        lines = []
        for item in results:
            lines.append(f"- {item.path}: {item.html_url}")
        if not lines:
            return f"Nothing found for '{query}' in {repo_name}"
        return "\n".join(lines)


class ReadRepositoryFileInput(BaseModel):
    repo_name: str = Field(description="Exact repository name, e.g. 'check_server'")
    file_path: str = Field(description="Path to the file inside the repository, e.g. 'src/main.py'")


class ReadRepositoryFileTool(LoggedTool):
    name: str = "ReadRepositoryFile"
    description: str = (
        "Read the full contents of a specific file from a GitHub repository. "
        "Use SearchInRepository first to find the file path, then call this to read it."
    )
    args_schema: type[BaseModel] = ReadRepositoryFileInput

    def _run(self, repo_name: str, file_path: str) -> str:
        auth = Auth.Token(settings.GITHUB_TOKEN)
        git = Github(auth=auth)

        repo = git.get_user().get_repo(repo_name)
        content = repo.get_contents(file_path)
        return content.decoded_content.decode("utf-8")


# tests
if __name__ == "__main__":
    tool = ListRepositoriesTool()
    print(tool.run())
