"""
Seed agent and tool config tables from the agent registry.

Called once on app startup. Safe to run multiple times — uses upsert logic:
- New agents/tools are inserted with is_enabled=True
- Existing rows are NOT touched (user config is preserved)
"""
import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger()


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
    logger.info("seed_complete")
