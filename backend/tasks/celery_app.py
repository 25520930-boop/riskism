"""
Riskism - Celery Configuration & Scheduled Tasks
"""
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


@app.task(bind=True, name='backend.tasks.celery_app.run_morning_analysis')
def run_morning_analysis(self):
    """Celery task: Morning analysis."""
    from backend.agent.orchestrator import AgentOrchestrator
    agent = AgentOrchestrator()
    result = agent.run_morning_analysis(user_id=1)
    return {'status': 'completed', 'insight_title': result.get('insight', {}).get('title', '')}


@app.task(bind=True, name='backend.tasks.celery_app.run_afternoon_review')
def run_afternoon_review(self):
    """Celery task: Afternoon review with self-reflection."""
    from backend.agent.orchestrator import AgentOrchestrator
    agent = AgentOrchestrator()
    result = agent.run_afternoon_review(user_id=1)
    return {'status': 'completed', 'accuracy': result.get('reflection', {}).get('accuracy_score', 0)}
