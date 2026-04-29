"""
Celery tasks for the IT-company workers.

run_orchestrator: the main task — receives a user message,
runs ChiefOrchestrator, saves results.
"""
import structlog

from app.core.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.run_orchestrator",
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def run_orchestrator(self, task_id: int, chat_id: int, user_message: str) -> dict:
    """
    Execute the full orchestration pipeline for a user message.
    Updates the Task record status throughout execution.
    """
    # Import inside task to avoid circular imports and ensure fresh DB connection
    from app.db.session import SessionLocal
    from app.models.task import Task
    from app.orchestrator.orchestrator import Orchestrator

    logger.info(
        "Orchestrator task started",
        celery_task_id=self.request.id,
        task_id=task_id,
        chat_id=chat_id,
        message_preview=user_message[:100],
    )

    db = SessionLocal()
    db_task = None

    try:
        # Mark task as running
        db_task = db.query(Task).filter(Task.id == task_id).first()
        if db_task:
            db_task.status = "running"
            db.commit()

        orchestrator = Orchestrator(db)
        result = orchestrator.run(chat_id, user_message, task_id)

        # Mark task as completed
        if db_task:
            db_task.status = "completed"
            db.commit()

        logger.info(
            "Orchestrator task completed",
            task_id=task_id,
            agents_used=result.selected_agents,
            has_errors=bool(result.errors),
        )
        return result.to_dict()

    except Exception as exc:
        logger.error(
            "Orchestrator task failed",
            task_id=task_id,
            error=str(exc),
            exc_info=True,
        )

        # Mark task as failed before retrying
        if db_task:
            db_task.status = "failed"
            db.commit()

        try:
            raise self.retry(exc=exc, countdown=30)
        except self.MaxRetriesExceededError:
            logger.error("Max retries exceeded", task_id=task_id, error=str(exc))
            return {"error": str(exc), "task_id": task_id}

    finally:
        db.close()
