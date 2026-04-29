"""
DockerInspectTool — reads and analyzes Docker/env configuration from sample_data.
"""
import os
from pydantic import BaseModel, Field

from app.tools.base import LoggedTool
from app.config import settings


class DockerInspectInput(BaseModel):
    target: str = Field(
        default="docker-compose",
        description=(
            "What to inspect: 'docker-compose' for docker-compose-sample.yml, "
            "'env' for .env example, 'all' for everything."
        ),
    )


class DockerInspectTool(LoggedTool):
    name: str = "DockerInspect"
    description: str = (
        "Read and analyze Docker Compose configuration and environment variables. "
        "Checks for common misconfigurations, missing env vars, and deployment issues. "
        "target options: docker-compose, env, all"
    )
    args_schema: type[BaseModel] = DockerInspectInput

    def _run(self, target: str = "docker-compose") -> str:
        results = []

        if target in ("docker-compose", "all"):
            dc_path = os.path.join(settings.SAMPLE_DATA_PATH, "docker-compose-sample.yml")
            if os.path.exists(dc_path):
                with open(dc_path, "r") as f:
                    content = f.read()
                results.append(f"=== docker-compose-sample.yml ===\n{content}")

                # Basic checks
                checks = []
                if "healthcheck" not in content:
                    checks.append("WARNING: No healthchecks defined for services")
                if "restart:" not in content and "restart_policy:" not in content:
                    checks.append("WARNING: No restart policy defined — services won't auto-recover")
                if "${" not in content and "env_file" not in content:
                    checks.append("INFO: Env vars appear hardcoded — consider using .env file")
                if checks:
                    results.append("\nAnalysis:\n" + "\n".join(f"  {c}" for c in checks))
            else:
                results.append("docker-compose-sample.yml not found in sample_data/")

        if target in ("env", "all"):
            env_path = os.path.join(settings.SAMPLE_DATA_PATH, ".env.sample")
            if not os.path.exists(env_path):
                # Try the project root .env.example as fallback
                env_path = os.path.join(os.path.dirname(settings.SAMPLE_DATA_PATH), ".env.example")

            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    content = f.read()
                results.append(f"\n=== Environment Variables ===\n{content}")

                # Check for empty required vars
                empty_vars = []
                for line in content.splitlines():
                    if "=" in line and not line.startswith("#"):
                        key, _, value = line.partition("=")
                        if not value.strip():
                            empty_vars.append(key.strip())
                if empty_vars:
                    results.append(
                        f"\nWARNING: Empty variables: {', '.join(empty_vars)}"
                    )
            else:
                results.append("\n.env.sample not found")

        return "\n".join(results) if results else "No configuration files found."
