"""
Riskism - Celery Configuration & Scheduled Tasks
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab

from backend.config import get_settings

settings = get_settings()

app = Celery(
    'riskism',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone=settings.market_timezone,
    enable_utc=False,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max
    worker_max_tasks_per_child=50,
)

# Scheduled tasks: Morning analysis + Afternoon review
app.conf.beat_schedule = {
    'morning-analysis': {
        'task': 'backend.tasks.celery_app.run_morning_analysis',
        'schedule': crontab(hour=8, minute=30, day_of_week='1-5'),  # Mon-Fri 8:30 AM
    },
    'afternoon-review': {
        'task': 'backend.tasks.celery_app.run_afternoon_review',
        'schedule': crontab(hour=15, minute=30, day_of_week='1-5'),  # Mon-Fri 3:30 PM
    },
}


def _day_window():
    tz = ZoneInfo(settings.market_timezone)
    start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def _user_has_holdings(user_id: int) -> bool:
    from sqlalchemy import text
    from backend.database import SyncSessionLocal

    db = None
    try:
        db = SyncSessionLocal()
        row = db.execute(
            text("SELECT 1 FROM portfolios WHERE user_id = :uid AND quantity > 0 LIMIT 1"),
            {"uid": user_id}
        ).fetchone()
        return bool(row)
    finally:
        if db:
            db.close()


def _has_morning_prediction_today(user_id: int) -> bool:
    from sqlalchemy import text
    from backend.database import SyncSessionLocal

    start, end = _day_window()
    db = None
    try:
        db = SyncSessionLocal()
        row = db.execute(
            text(
                "SELECT 1 FROM morning_predictions "
                "WHERE user_id = :uid AND predicted_at >= :start AND predicted_at < :end "
                "LIMIT 1"
            ),
            {"uid": user_id, "start": start, "end": end}
        ).fetchone()
        return bool(row)
    finally:
        if db:
            db.close()


def _has_reflection_today(user_id: int) -> bool:
    from sqlalchemy import text
    from backend.database import SyncSessionLocal

    start, end = _day_window()
    db = None
    try:
        db = SyncSessionLocal()
        row = db.execute(
            text(
                "SELECT 1 FROM reflections "
                "WHERE user_id = :uid AND evaluated_at >= :start AND evaluated_at < :end "
                "LIMIT 1"
            ),
            {"uid": user_id, "start": start, "end": end}
        ).fetchone()
        return bool(row)
    finally:
        if db:
            db.close()


@app.task(bind=True, name='backend.tasks.celery_app.run_morning_analysis')
def run_morning_analysis(self):
    """Celery task: Morning analysis."""
    user_id = 1
    if not _user_has_holdings(user_id):
        return {'status': 'skipped', 'reason': 'no_holdings'}
    if _has_morning_prediction_today(user_id):
        return {'status': 'skipped', 'reason': 'already_ran_today'}

    import asyncio
    from backend.agent.orchestrator import AgentOrchestrator
    agent = AgentOrchestrator()
    result = asyncio.run(agent.run_morning_analysis(user_id=user_id))
    return {'status': 'completed', 'insight_title': result.get('insight', {}).get('title', '')}


@app.task(bind=True, name='backend.tasks.celery_app.run_afternoon_review')
def run_afternoon_review(self):
    """Celery task: Afternoon review with self-reflection."""
    user_id = 1
    if not _user_has_holdings(user_id):
        return {'status': 'skipped', 'reason': 'no_holdings'}
    if not _has_morning_prediction_today(user_id):
        return {'status': 'skipped', 'reason': 'missing_morning_prediction'}
    if _has_reflection_today(user_id):
        return {'status': 'skipped', 'reason': 'already_ran_today'}

    import asyncio
    from backend.agent.orchestrator import AgentOrchestrator
    agent = AgentOrchestrator()
    result = asyncio.run(agent.run_afternoon_review(user_id=user_id))
    return {'status': 'completed', 'accuracy': result.get('reflection', {}).get('accuracy_score', 0)}
