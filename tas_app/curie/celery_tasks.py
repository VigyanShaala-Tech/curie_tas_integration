"""Celery task for CURIE trigger delivery. No edx-platform imports (safe on LMS and CMS workers).

The function body imports delivery lazily so CELERY_IMPORTS can load this module
before Django apps are ready.
"""

from celery import shared_task


@shared_task(bind=True, max_retries=3, name="tas_app.curie.celery_tasks.deliver_curie_trigger")
def deliver_curie_trigger(self, trigger_id, callback_url=None):
    """
    Deliver one frozen CURIE trigger. Initial attempt plus three retries
    (jittered 15s / 60s / 240s) on connection errors, timeouts, 429 and 5xx.
    """
    from tas_app.curie.delivery import run_deliver_curie_trigger

    run_deliver_curie_trigger(self, trigger_id, callback_url)
