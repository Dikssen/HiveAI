from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.integration_config_helper import invalidate_cache
from app.models.integration_config import IntegrationConfig
from app.schemas.integration_config import IntegrationConfigResponse, IntegrationConfigUpdate

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationConfigResponse])
def list_integrations(db: Session = Depends(get_db)):
    return db.query(IntegrationConfig).order_by(IntegrationConfig.key).all()


@router.get("/{key}", response_model=IntegrationConfigResponse)
def get_integration(key: str, db: Session = Depends(get_db)):
    row = db.query(IntegrationConfig).filter(IntegrationConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Integration config not found")
    return row


@router.patch("/{key}", response_model=IntegrationConfigResponse)
def update_integration(key: str, body: IntegrationConfigUpdate, db: Session = Depends(get_db)):
    row = db.query(IntegrationConfig).filter(IntegrationConfig.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Integration config not found")
    row.value = body.value
    db.commit()
    db.refresh(row)
    invalidate_cache(key)
    return row
