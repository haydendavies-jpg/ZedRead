"""Celery application factory for ZedRead background tasks.

Connects to Redis as the broker and result backend.
The REDIS_URL environment variable must be set in production;
defaults to localhost for local development.

Tasks are discovered automatically from app/tasks/.
"""

import os

from celery import Celery

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "zedread",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.license_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Nightly expiry task — runs at 02:00 UTC every day
    beat_schedule={
        "expire-overdue-licenses": {
            "task": "app.tasks.license_tasks.expire_overdue_licenses",
            "schedule": 86400,  # Every 24 hours; adjust to crontab in production
        },
    },
)
