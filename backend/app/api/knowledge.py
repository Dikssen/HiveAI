from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.knowledge_entry import KnowledgeEntry
from app.schemas.knowledge import (
    KnowledgeEntryCreate,
    KnowledgeEntryUpdate,
    KnowledgeEntryResponse,
    KnowledgeEntryListResponse,
)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeEntryListResponse])
def list_entries(agent_name: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(KnowledgeEntry)
    if agent_name is not None:
        q = q.filter(KnowledgeEntry.agent_name == agent_name if agent_name else KnowledgeEntry.agent_name.is_(None))
    return q.order_by(KnowledgeEntry.updated_at.desc()).all()


@router.get("/{entry_id}", response_model=KnowledgeEntryResponse)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    return entry


@router.post("", response_model=KnowledgeEntryResponse, status_code=201)
def create_entry(body: KnowledgeEntryCreate, db: Session = Depends(get_db)):
    existing = db.query(KnowledgeEntry).filter(
        KnowledgeEntry.title == body.title,
        KnowledgeEntry.agent_name == body.agent_name,
    ).first()
    if existing:
        scope = f"agent '{body.agent_name}'" if body.agent_name else "global"
        raise HTTPException(status_code=409, detail=f"Entry '{body.title}' already exists for {scope}")
    entry = KnowledgeEntry(title=body.title, content=body.content, tags=body.tags, agent_name=body.agent_name)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.patch("/{entry_id}", response_model=KnowledgeEntryResponse)
def update_entry(entry_id: int, body: KnowledgeEntryUpdate, db: Session = Depends(get_db)):
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    if body.title is not None:
        entry.title = body.title
    if body.content is not None:
        entry.content = body.content
    if body.tags is not None:
        entry.tags = body.tags
    if body.agent_name is not None:
        entry.agent_name = body.agent_name
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    db.delete(entry)
    db.commit()
