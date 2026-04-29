import os
from pathlib import Path
from pydantic import BaseModel, Field
from git import Repo, InvalidGitRepositoryError, GitCommandError
from app.tools.base import LoggedTool
from app.config import settings

REPOS_ROOT = Path("/app/repos")


def _get_clone_url(repo_name: str) -> str:
    token = settings.GITHUB_TOKEN
    username = _get_github_username()
    if token:
        return f"https://{token}@github.com/{username}/{repo_name}.git"
    return f"https://github.com/{username}/{repo_name}.git"


def _get_github_username() -> str:
    from github import Github, Auth
    git = Github(auth=Auth.Token(settings.GITHUB_TOKEN))
    return git.get_user().login


def _repo_path(repo_name: str) -> Path:
    return REPOS_ROOT / repo_name


# ---------------------------------------------------------------------------

class CloneOrUpdateRepoInput(BaseModel):
    repo_name: str = Field(description="Repository name to clone or update, e.g. 'check_server'")
    branch: str = Field(default="", description="Branch to checkout. Empty means default branch.")


class CloneOrUpdateRepoTool(LoggedTool):
    name: str = "CloneOrUpdateRepo"
    description: str = (
        "Clone a GitHub repository locally if it does not exist, or pull latest changes if it does. "
        "Optionally switch to a specific branch. "
        "Always call this before reading files from a repository."
    )
    args_schema: type[BaseModel] = CloneOrUpdateRepoInput

    def _run(self, repo_name: str, branch: str = "") -> str:
        path = _repo_path(repo_name)
        REPOS_ROOT.mkdir(parents=True, exist_ok=True)

        if path.exists():
            repo = Repo(path)
            if branch and repo.active_branch.name != branch:
                repo.git.checkout(branch)
            repo.remotes.origin.pull()
            active = repo.active_branch.name
            return f"Updated '{repo_name}' (branch: {active}) at {path}"
        else:
            url = _get_clone_url(repo_name)
            repo = Repo.clone_from(url, path)
            if branch:
                repo.git.checkout(branch)
            active = repo.active_branch.name
            return f"Cloned '{repo_name}' (branch: {active}) to {path}"


# ---------------------------------------------------------------------------

class ListBranchesInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")


class ListBranchesTool(LoggedTool):
    name: str = "ListBranches"
    description: str = (
        "List all available branches in a locally cloned repository. "
        "Use CloneOrUpdateRepo first. Shows current active branch with '*'."
    )
    args_schema: type[BaseModel] = ListBranchesInput

    def _run(self, repo_name: str) -> str:
        path = _repo_path(repo_name)
        if not path.exists():
            return f"Repository '{repo_name}' is not cloned yet. Use CloneOrUpdateRepo first."

        repo = Repo(path)
        current = repo.active_branch.name
        remote_refs = repo.remotes.origin.refs
        branches = []
        for ref in remote_refs:
            name = ref.remote_head
            if name == "HEAD":
                continue
            marker = "* " if name == current else "  "
            branches.append(f"{marker}{name}")
        return "\n".join(branches) if branches else "No branches found."


# ---------------------------------------------------------------------------

class SwitchBranchInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    branch: str = Field(description="Branch name to switch to, e.g. 'develop' or 'feature/auth'")


class SwitchBranchTool(LoggedTool):
    name: str = "SwitchBranch"
    description: str = (
        "Switch to a different branch in a locally cloned repository. "
        "Use ListBranches to see available branches first."
    )
    args_schema: type[BaseModel] = SwitchBranchInput

    def _run(self, repo_name: str, branch: str) -> str:
        path = _repo_path(repo_name)
        if not path.exists():
            return f"Repository '{repo_name}' is not cloned yet. Use CloneOrUpdateRepo first."

        repo = Repo(path)
        repo.git.checkout(branch)
        return f"Switched '{repo_name}' to branch '{branch}'"


# ---------------------------------------------------------------------------

class ListLocalFilesInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    path: str = Field(default="", description="Subdirectory to list. Empty for repo root.")


class ListLocalFilesTool(LoggedTool):
    name: str = "ListLocalFiles"
    description: str = (
        "List files and directories in a locally cloned repository. "
        "Use CloneOrUpdateRepo first. Pass a subdirectory path to explore deeper."
    )
    args_schema: type[BaseModel] = ListLocalFilesInput

    def _run(self, repo_name: str, path: str = "") -> str:
        base = _repo_path(repo_name)
        if not base.exists():
            return f"Repository '{repo_name}' is not cloned yet. Use CloneOrUpdateRepo first."

        target = base / path if path else base
        if not target.exists():
            return f"Path '{path}' does not exist in '{repo_name}'"

        lines = []
        for item in sorted(target.iterdir()):
            if item.name == ".git":
                continue
            prefix = "[dir] " if item.is_dir() else "[file]"
            rel = item.relative_to(base)
            lines.append(f"{prefix} {rel}")
        return "\n".join(lines) if lines else "Directory is empty."


# ---------------------------------------------------------------------------

class ReadLocalFileInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    file_path: str = Field(description="File path relative to repo root, e.g. 'src/main.py'")


class ReadLocalFileTool(LoggedTool):
    name: str = "ReadLocalFile"
    description: str = (
        "Read the contents of a file from a locally cloned repository. "
        "Use ListLocalFiles first to find the correct file path."
    )
    args_schema: type[BaseModel] = ReadLocalFileInput

    def _run(self, repo_name: str, file_path: str) -> str:
        path = _repo_path(repo_name) / file_path
        if not path.exists():
            return f"File '{file_path}' not found in '{repo_name}'"
        if not path.is_file():
            return f"'{file_path}' is a directory, not a file. Use ListLocalFiles to explore it."

        size = path.stat().st_size
        if size > 100_000:
            return f"File is too large ({size} bytes). Read specific sections instead."

        return path.read_text(errors="replace")
