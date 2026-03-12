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

    # settings.SOCIAL_AUTH_REDIRECT_IS_HTTPS = True
    # SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
