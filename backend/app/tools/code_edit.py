"""
Block-level code editing tools.
Agents use these to read and modify specific functions/classes or line ranges
instead of rewriting entire files.
"""
import ast
from pathlib import Path

from pydantic import BaseModel, Field

from app.tools.base import LoggedTool

REPOS_ROOT = Path("/app/repos")


def _repo_file(repo_name: str, file_path: str) -> Path:
    root = REPOS_ROOT / repo_name
    target = (root / file_path).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise ValueError(f"Path '{file_path}' is outside the repository root.")
    return target


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def _find_symbol_lines(source: str, symbol_name: str) -> tuple[int, int] | None:
    """
    Return (start_line, end_line) 1-based inclusive for a top-level or nested
    function/class named symbol_name. Uses Python AST; returns None if not found
    or if the file is not valid Python.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol_name and hasattr(node, "end_lineno"):
                return node.lineno, node.end_lineno
    return None


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

class CodeReadRangeInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    file_path: str = Field(description="File path relative to repo root, e.g. 'src/main.py'")
    start_line: int = Field(description="First line to read (1-based, inclusive)")
    end_line: int = Field(description="Last line to read (1-based, inclusive)")


class CodeReadRangeTool(LoggedTool):
    name: str = "CodeReadRange"
    description: str = (
        "Read a specific range of lines from a file in a local repository. "
        "Returns lines with line numbers so you can reference them precisely. "
        "Use this to inspect a section of a large file without reading the whole thing."
    )
    args_schema: type[BaseModel] = CodeReadRangeInput

    def _run(self, repo_name: str, file_path: str, start_line: int, end_line: int) -> str:
        try:
            path = _repo_file(repo_name, file_path)
        except ValueError as e:
            return str(e)
        if not path.exists():
            return f"File '{file_path}' not found in '{repo_name}'."

        lines = _read_lines(path)
        total = len(lines)
        start = max(1, start_line)
        end = min(total, end_line)
        if start > total:
            return f"start_line {start_line} exceeds file length ({total} lines)."

        result = []
        for i, line in enumerate(lines[start - 1 : end], start=start):
            result.append(f"{i:>5}: {line.rstrip()}")
        return "\n".join(result)


class CodeReadSymbolInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    file_path: str = Field(description="File path relative to repo root, e.g. 'src/main.py'")
    symbol_name: str = Field(description="Function or class name to read, e.g. 'process_order'")


class CodeReadSymbolTool(LoggedTool):
    name: str = "CodeReadSymbol"
    description: str = (
        "Read a specific function or class by name from a Python file. "
        "Returns the full definition with line numbers. "
        "Much faster than reading the whole file when you know the symbol name."
    )
    args_schema: type[BaseModel] = CodeReadSymbolInput

    def _run(self, repo_name: str, file_path: str, symbol_name: str) -> str:
        try:
            path = _repo_file(repo_name, file_path)
        except ValueError as e:
            return str(e)
        if not path.exists():
            return f"File '{file_path}' not found in '{repo_name}'."

        source = path.read_text(encoding="utf-8", errors="replace")
        result = _find_symbol_lines(source, symbol_name)
        if result is None:
            return (
                f"Symbol '{symbol_name}' not found in '{file_path}'. "
                "Note: only Python files support AST search. "
                "Use CodeReadRange with a known line range for other languages."
            )
        start, end = result
        lines = source.splitlines()
        block = [f"{i:>5}: {lines[i - 1]}" for i in range(start, end + 1)]
        return f"# {symbol_name} — lines {start}–{end}\n" + "\n".join(block)


# ---------------------------------------------------------------------------
# Write tools
# ---------------------------------------------------------------------------

class CodeReplaceRangeInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    file_path: str = Field(description="File path relative to repo root, e.g. 'src/main.py'")
    start_line: int = Field(description="First line to replace (1-based, inclusive)")
    end_line: int = Field(description="Last line to replace (1-based, inclusive)")
    new_content: str = Field(description="Replacement content (replaces lines start_line through end_line)")


class CodeReplaceRangeTool(LoggedTool):
    name: str = "CodeReplaceRange"
    description: str = (
        "Replace a specific range of lines in a file with new content. "
        "Only the lines between start_line and end_line are changed — "
        "the rest of the file is untouched. "
        "Always use CodeReadRange or CodeReadSymbol first to confirm line numbers."
    )
    args_schema: type[BaseModel] = CodeReplaceRangeInput

    def _run(
        self, repo_name: str, file_path: str, start_line: int, end_line: int, new_content: str
    ) -> str:
        try:
            path = _repo_file(repo_name, file_path)
        except ValueError as e:
            return str(e)
        if not path.exists():
            return f"File '{file_path}' not found in '{repo_name}'."

        lines = _read_lines(path)
        total = len(lines)
        if start_line < 1 or start_line > total:
            return f"start_line {start_line} is out of range (file has {total} lines)."
        if end_line < start_line or end_line > total:
            return f"end_line {end_line} is out of range (file has {total} lines)."

        replacement = new_content if new_content.endswith("\n") else new_content + "\n"
        new_lines = lines[: start_line - 1] + [replacement] + lines[end_line:]
        path.write_text("".join(new_lines), encoding="utf-8")
        replaced = end_line - start_line + 1
        return (
            f"Replaced lines {start_line}–{end_line} ({replaced} lines) "
            f"in '{file_path}' in '{repo_name}'."
        )


class CodeReplaceSymbolInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    file_path: str = Field(description="File path relative to repo root, e.g. 'src/main.py'")
    symbol_name: str = Field(description="Name of the function or class to replace")
    new_content: str = Field(description="Complete new definition of the function or class")


class CodeReplaceSymbolTool(LoggedTool):
    name: str = "CodeReplaceSymbol"
    description: str = (
        "Find a function or class by name in a Python file and replace its entire definition. "
        "Everything else in the file stays unchanged. "
        "Provide the complete new definition in new_content (including the def/class line)."
    )
    args_schema: type[BaseModel] = CodeReplaceSymbolInput

    def _run(self, repo_name: str, file_path: str, symbol_name: str, new_content: str) -> str:
        try:
            path = _repo_file(repo_name, file_path)
        except ValueError as e:
            return str(e)
        if not path.exists():
            return f"File '{file_path}' not found in '{repo_name}'."

        source = path.read_text(encoding="utf-8", errors="replace")
        result = _find_symbol_lines(source, symbol_name)
        if result is None:
            return (
                f"Symbol '{symbol_name}' not found in '{file_path}'. "
                "Only Python files are supported. Use CodeReplaceRange for other languages."
            )
        start, end = result
        lines = source.splitlines(keepends=True)
        replacement = new_content if new_content.endswith("\n") else new_content + "\n"
        new_lines = lines[: start - 1] + [replacement] + lines[end:]
        path.write_text("".join(new_lines), encoding="utf-8")
        return f"Symbol '{symbol_name}' (lines {start}–{end}) replaced in '{file_path}' in '{repo_name}'."


class CodeInsertAtLineInput(BaseModel):
    repo_name: str = Field(description="Repository name, e.g. 'check_server'")
    file_path: str = Field(description="File path relative to repo root, e.g. 'src/main.py'")
    line_number: int = Field(description="Line number reference (1-based)")
    position: str = Field(
        default="after",
        description="Where to insert relative to line_number: 'before' or 'after'",
    )
    content: str = Field(description="Content to insert")


class CodeInsertAtLineTool(LoggedTool):
    name: str = "CodeInsertAtLine"
    description: str = (
        "Insert new content before or after a specific line in a file. "
        "Does not remove or replace any existing lines. "
        "Use position='after' to add code after a function, "
        "or position='before' to add an import or decorator."
    )
    args_schema: type[BaseModel] = CodeInsertAtLineInput

    def _run(
        self, repo_name: str, file_path: str, line_number: int, position: str, content: str
    ) -> str:
        try:
            path = _repo_file(repo_name, file_path)
        except ValueError as e:
            return str(e)
        if not path.exists():
            return f"File '{file_path}' not found in '{repo_name}'."

        lines = _read_lines(path)
        total = len(lines)
        if line_number < 1 or line_number > total:
            return f"line_number {line_number} is out of range (file has {total} lines)."

        insertion = content if content.endswith("\n") else content + "\n"
        if position == "before":
            idx = line_number - 1
        else:
            idx = line_number

        new_lines = lines[:idx] + [insertion] + lines[idx:]
        path.write_text("".join(new_lines), encoding="utf-8")
        where = f"before line {line_number}" if position == "before" else f"after line {line_number}"
        return f"Content inserted {where} in '{file_path}' in '{repo_name}'."
