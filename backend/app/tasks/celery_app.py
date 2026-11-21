
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "gocomet",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.auction_lifecycle"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "process-auction-lifecycle-every-5-seconds": {
            "task": "app.tasks.auction_lifecycle.process_auction_lifecycle",
            "schedule": 5.0,
        },
    },
)
