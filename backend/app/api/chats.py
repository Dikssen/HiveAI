from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.chat import Chat
from app.models.message import Message
from app.models.task import Task
from app.schemas.chat import ChatCreate, ChatResponse, ChatDetailResponse
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.task import SendMessageResponse

router = APIRouter(prefix="/chats", tags=["chats"])


@router.post("", response_model=ChatResponse, status_code=201)
def create_chat(body: ChatCreate, db: Session = Depends(get_db)):
    chat = Chat(title=body.title or "New Chat")
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("", response_model=list[ChatResponse])
def list_chats(db: Session = Depends(get_db)):
    return (
        db.query(Chat)
        .filter(Chat.is_hidden == False)
        .order_by(Chat.created_at.desc())
        .all()
    )


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    chat.is_hidden = True
    db.commit()


@router.get("/{chat_id}", response_model=ChatDetailResponse)
def get_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.post("/{chat_id}/messages", response_model=SendMessageResponse, status_code=202)
def send_message(chat_id: int, body: MessageCreate, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Update chat title from first user message (before adding the new one)
    existing_user_messages = (
        db.query(Message).filter(Message.chat_id == chat_id, Message.role == "user").count()
    )
    if existing_user_messages == 0:
        chat.title = body.content[:80]

    # Persist user message
    user_msg = Message(chat_id=chat_id, role="user", content=body.content)
    db.add(user_msg)

    # Create task record
    task = Task(chat_id=chat_id, status="pending")
    db.add(task)
    db.commit()
    db.refresh(user_msg)
    db.refresh(task)

    # Dispatch Celery task
    from app.workers.tasks import run_orchestrator
    celery_result = run_orchestrator.apply_async(
        args=[task.id, chat_id, body.content],
        task_id=None,  # let Celery generate
    )

    task.celery_task_id = celery_result.id
    db.commit()

    return SendMessageResponse(
        message_id=user_msg.id,
        task_id=task.id,
        status="pending",
    )


@router.get("/{chat_id}/messages", response_model=list[MessageResponse])
def get_messages(chat_id: int, db: Session = Depends(get_db)):
    return (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )


@router.post("/{chat_id}/messages/stream")
async def send_message_stream(chat_id: int, body: MessageCreate, db: Session = Depends(get_db)):
    """
    Send a message and stream the orchestration progress + final answer via SSE.

    Events:
      {"type": "step",  "event": "planning"}
      {"type": "step",  "event": "decision", "agents": [...]}
      {"type": "step",  "event": "agent_start",    "agent": "...", "iteration": N}
      {"type": "step",  "event": "agent_complete", "agent": "...", "iteration": N}
      {"type": "step",  "event": "evaluating"}
      {"type": "step",  "event": "synthesizing"}
      {"type": "token", "content": "..."}
      {"type": "done",  "message_id": N}
      {"type": "error", "message": "...", "message_id": N}
    """
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    existing_user_messages = (
        db.query(Message).filter(Message.chat_id == chat_id, Message.role == "user").count()
    )
    if existing_user_messages == 0:
        chat.title = body.content[:80]

    user_msg = Message(chat_id=chat_id, role="user", content=body.content)
    db.add(user_msg)

    task = Task(chat_id=chat_id, status="running")
    db.add(task)
    db.commit()
    db.refresh(user_msg)
    db.refresh(task)

    from app.orchestrator.factory import get_streaming_orchestrator

    async def generate():
        orchestrator = get_streaming_orchestrator(db)
        completed = False
        try:
            async for event in orchestrator.stream(chat_id, body.content, task.id):
                yield event
                if '"type": "done"' in event or '"type": "error"' in event:
                    completed = True
        finally:
            task.status = "completed" if completed else "failed"
            db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
