import json
from celery import Celery
from kombu.serialization import register
from app.config import settings

register(
    "json_unicode",
    lambda obj: json.dumps(obj, ensure_ascii=False),
    json.loads,
    content_type="application/json",
    content_encoding="utf-8",
)

celery_app = Celery(
    "hiveai",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json_unicode",
    result_serializer="json_unicode",
    accept_content=["application/json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={"app.workers.tasks.*": {"queue": "default"}},
)
