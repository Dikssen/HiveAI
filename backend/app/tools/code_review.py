"""
CodeReviewTool — performs a basic static analysis on sample code or provided text.
"""
import os
import re
from pydantic import BaseModel, Field

from app.tools.base import LoggedTool
from app.config import settings


class CodeReviewInput(BaseModel):
    target: str = Field(
        default="sample",
        description=(
            "What to review: 'sample' to load sample_code.py, "
            "or provide actual code/text to review directly."
        ),
    )


class CodeReviewTool(LoggedTool):
    name: str = "CodeReview"
    description: str = (
        "Review Python code for common issues: missing error handling, "
        "hardcoded secrets, SQL injection risks, naming conventions, "
        "and structural problems. Pass 'sample' to review the sample code file."
    )
    args_schema: type[BaseModel] = CodeReviewInput

    def _run(self, target: str = "sample") -> str:
        if target.strip().lower() == "sample":
            file_path = os.path.join(settings.SAMPLE_DATA_PATH, "sample_code.py")
            if not os.path.exists(file_path):
                return "sample_code.py not found in sample_data/."
            with open(file_path, "r") as f:
                code = f.read()
            filename = "sample_code.py"
        else:
            code = target
            filename = "<provided code>"

        issues = []

        # Hardcoded secrets
        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']{3,}["\']', "Hardcoded password"),
            (r'api_key\s*=\s*["\'][^"\']{3,}["\']', "Hardcoded API key"),
            (r'secret\s*=\s*["\'][^"\']{3,}["\']', "Hardcoded secret"),
            (r'token\s*=\s*["\'][^"\']{3,}["\']', "Hardcoded token"),
        ]
        for pattern, label in secret_patterns:
            for m in re.finditer(pattern, code, re.IGNORECASE):
                line_no = code[: m.start()].count("\n") + 1
                issues.append(f"[CRITICAL] Line {line_no}: {label} detected")

        # Bare except
        for m in re.finditer(r"\bexcept\s*:", code):
            line_no = code[: m.start()].count("\n") + 1
            issues.append(f"[WARNING] Line {line_no}: Bare `except:` catches all exceptions — be specific")

        # print statements (debug leftovers)
        for m in re.finditer(r"^\s*print\(", code, re.MULTILINE):
            line_no = code[: m.start()].count("\n") + 1
            issues.append(f"[INFO] Line {line_no}: `print()` found — consider using logging")

        # SQL string concatenation (basic injection risk)
        for m in re.finditer(r'execute\s*\([^)]*\+', code):
            line_no = code[: m.start()].count("\n") + 1
            issues.append(f"[CRITICAL] Line {line_no}: Possible SQL injection via string concatenation")

        # TODO/FIXME comments
        for m in re.finditer(r"#\s*(TODO|FIXME|HACK|XXX)", code, re.IGNORECASE):
            line_no = code[: m.start()].count("\n") + 1
            tag = m.group(1).upper()
            issues.append(f"[INFO] Line {line_no}: {tag} comment found")

        # Missing type hints on function defs
        func_defs = re.findall(r"def \w+\([^)]*\)(?!\s*->)", code)
        if func_defs:
            issues.append(
                f"[INFO] {len(func_defs)} function(s) missing return type annotation"
            )

        summary = f"Code Review: {filename}\n{'=' * 40}\n"
        summary += f"Lines of code: {len(code.splitlines())}\n"
        summary += f"Issues found: {len(issues)}\n\n"

        if issues:
            summary += "Issues:\n" + "\n".join(f"  {i}" for i in issues)
        else:
            summary += "No issues detected."

        return summary
