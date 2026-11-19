"""Job queue wiring (SMPLSGHT-18).

Collection runs on an RQ (Redis Queue) worker instead of blocking the request. The API
enqueues a job and returns immediately; a worker picks it up and persists results, and the
investigation's status reflects progress.

`queue_eager` (settings) runs the task inline with no Redis — convenient for local dev and
used by the test suite — so the same code path works with or without a worker.
"""

from __future__ import annotations

from redis import Redis
from rq import Queue

from app.core.config import settings

# Fully-qualified task path so the worker (a separate process) can import it.
_TASK = "app.tasks.run_investigation_task"


def get_redis() -> Redis:
    return Redis.from_url(settings.redis_url)


def get_queue() -> Queue:
    return Queue(settings.collection_queue, connection=get_redis())


def enqueue_investigation_run(investigation_id: str) -> str:
    """Enqueue a collection run. Returns the job id (or "eager" when run inline)."""
    if settings.queue_eager:
        from app.tasks import run_investigation_task

        run_investigation_task(investigation_id)
        return "eager"

    job = get_queue().enqueue(_TASK, investigation_id)
    return job.id
