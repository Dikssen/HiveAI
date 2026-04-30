"""
Seed agent/tool config tables and integration configs on app startup.

Safe to run multiple times — uses upsert logic:
- New rows are inserted; existing rows are NOT touched (user config is preserved)
"""
import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()

_INTEGRATION_DEFAULTS = [
    ("GITHUB_TOKEN",             None, True,  "GitHub personal access token"),
    ("CONFLUENCE_URL",           None, False, "Confluence base URL, e.g. https://mycompany.atlassian.net/wiki"),
    ("CONFLUENCE_USER",          None, False, "Confluence login email"),
    ("CONFLUENCE_API_TOKEN",     None, True,  "Confluence API token"),
    ("CONFLUENCE_SPACE_KEY",     None, False, "Default Confluence space key, e.g. DEV"),
    ("CONFLUENCE_WRITE_ENABLED", None, False, "Allow agents to create/edit Confluence pages (true/false)"),
    ("JIRA_URL",                 None, False, "Jira base URL, e.g. https://mycompany.atlassian.net"),
    ("JIRA_USER",                None, False, "Jira login email"),
    ("JIRA_API_TOKEN",           None, True,  "Jira API token"),
    ("JIRA_PROJECT_KEY",         None, False, "Default Jira project key, e.g. DEV"),
    ("JIRA_WRITE_ENABLED",       None, False, "Allow agents to create/update Jira issues (true/false)"),
    ("FLEIO_DB_HOST",            None, False, "Fleio MySQL host, e.g. 127.0.0.1"),
    ("FLEIO_DB_PORT",            None, False, "Fleio MySQL port (default 3306)"),
    ("FLEIO_DB_USER",            None, False, "Fleio MySQL user"),
    ("FLEIO_DB_PASSWORD",        None, True,  "Fleio MySQL password"),
    ("FLEIO_DB_NAME",            None, False, "Fleio MySQL database name, e.g. fleio"),
]


def seed_integration_configs(db: Session) -> None:
    from app.models.integration_config import IntegrationConfig

    for key, _unused, is_secret, description in _INTEGRATION_DEFAULTS:
        existing = db.query(IntegrationConfig).filter(IntegrationConfig.key == key).first()
        if existing:
            continue
        db.add(IntegrationConfig(key=key, value=None, is_secret=is_secret, description=description))
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
