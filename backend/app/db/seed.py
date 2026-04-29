"""
Seed agent/tool config tables and integration configs on app startup.

Safe to run multiple times — uses upsert logic:
- New rows are inserted; existing rows are NOT touched (user config is preserved)
"""
import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()

_INTEGRATION_DEFAULTS = [
    ("GITHUB_TOKEN",          "GITHUB_TOKEN",          True,  "GitHub personal access token"),
    ("CONFLUENCE_URL",        "CONFLUENCE_URL",         False, "Confluence base URL, e.g. https://mycompany.atlassian.net/wiki"),
    ("CONFLUENCE_USER",       "CONFLUENCE_USER",        False, "Confluence login email"),
    ("CONFLUENCE_API_TOKEN",  "CONFLUENCE_API_TOKEN",   True,  "Confluence API token"),
    ("CONFLUENCE_SPACE_KEY",  "CONFLUENCE_SPACE_KEY",   False, "Default Confluence space key, e.g. DEV"),
    ("CONFLUENCE_WRITE_ENABLED", "CONFLUENCE_WRITE_ENABLED", False, "Allow agents to create/edit Confluence pages (true/false)"),
]


def seed_integration_configs(db: Session) -> None:
    from app.config import settings
    from app.models.integration_config import IntegrationConfig

    for key, settings_attr, is_secret, description in _INTEGRATION_DEFAULTS:
        existing = db.query(IntegrationConfig).filter(IntegrationConfig.key == key).first()
        if existing:
            continue
        env_value = getattr(settings, settings_attr, None)
        if isinstance(env_value, bool):
            env_value = str(env_value).lower()
        db.add(IntegrationConfig(
            key=key,
            value=str(env_value) if env_value is not None else None,
            is_secret=is_secret,
            description=description,
        ))
        logger.info("seed_integration_created", key=key)

    db.commit()


def seed_agents_and_tools(db: Session) -> None:
    from app.agents.agent_registry import AGENT_REGISTRY
    from app.models.agent import Agent
    from app.models.agent_tool_config import AgentToolConfig

    for agent_name, agent_impl in AGENT_REGISTRY.items():
        # Upsert agent row
        agent_row = db.query(Agent).filter(Agent.name == agent_name).first()
        if not agent_row:
            agent_row = Agent(
                name=agent_name,
                role=agent_impl.role,
                description=agent_impl.description,
            )
            db.add(agent_row)
            db.flush()
            logger.info("seed_agent_created", agent=agent_name)
        else:
            # Keep is_enabled as-is, just sync metadata
            agent_row.role = agent_impl.role
            agent_row.description = agent_impl.description

        # Upsert tool config rows
        all_tools = agent_impl.get_tools()
        for tool in all_tools:
            tool_name = type(tool).__name__
            existing = (
                db.query(AgentToolConfig)
                .filter(AgentToolConfig.agent_id == agent_row.id, AgentToolConfig.tool_name == tool_name)
                .first()
            )
            if not existing:
                db.add(AgentToolConfig(agent_id=agent_row.id, tool_name=tool_name, is_enabled=True))
                logger.info("seed_tool_created", agent=agent_name, tool=tool_name)

    db.commit()
    seed_integration_configs(db)
    logger.info("seed_complete")
