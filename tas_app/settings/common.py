"""
Common Pluggable Django App settings

Handling of environment variables, see: https://django-environ.readthedocs.io/en/latest/
to convert .env to yml see: https://django-environ.readthedocs.io/en/latest/tips.html#docker-style-file-based-variables
"""

from path import Path as path
import environ
import os

# path to this file.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))


APP_ROOT = path(__file__).abspath().dirname().dirname()  # /blah/blah/blah/.../example_grades
REPO_ROOT = APP_ROOT.dirname()  # /blah/blah/blah/.../example-digital-learning-openedx
TEMPLATES_DIR = APP_ROOT / "templates"


def plugin_settings(settings):
    """
    Injects local settings into django settings
    """

    settings.CURIE_ENABLED = getattr(settings, "CURIE_ENABLED", False)
    settings.CURIE_TRIGGER_URL = getattr(settings, "CURIE_TRIGGER_URL", "")
    settings.CURIE_CALLBACK_BASE_URL = getattr(settings, "CURIE_CALLBACK_BASE_URL", "")
    settings.CURIE_AUTH_HEADER_NAME = getattr(settings, "CURIE_AUTH_HEADER_NAME", "")
    settings.CURIE_SHARED_SECRET = getattr(settings, "CURIE_SHARED_SECRET", "")
    settings.CURIE_CONNECT_TIMEOUT_SECONDS = getattr(settings, "CURIE_CONNECT_TIMEOUT_SECONDS", 3)
    settings.CURIE_REQUEST_TIMEOUT_SECONDS = getattr(settings, "CURIE_REQUEST_TIMEOUT_SECONDS", 10)
    settings.CURIE_REVIEW_TIMEOUT_SECONDS = getattr(settings, "CURIE_REVIEW_TIMEOUT_SECONDS", 300)
    settings.CURIE_REVIEW_MAX_WAIT_SECONDS = getattr(settings, "CURIE_REVIEW_MAX_WAIT_SECONDS", 1800)
    settings.CURIE_COMPONENT_PASS_THRESHOLD = getattr(settings, "CURIE_COMPONENT_PASS_THRESHOLD", 6.0)

    imports = list(getattr(settings, "CELERY_IMPORTS", []) or [])
    if "tas_app.curie.celery_tasks" not in imports:
        imports.append("tas_app.curie.celery_tasks")
    settings.CELERY_IMPORTS = imports
