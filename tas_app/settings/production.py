"""
Common Pluggable Django App settings
"""


def plugin_settings(settings):
    """
    Injects local settings into django settings
    """
    imports = list(getattr(settings, "CELERY_IMPORTS", []) or [])
    if "tas_app.curie.celery_tasks" not in imports:
        imports.append("tas_app.curie.celery_tasks")
    settings.CELERY_IMPORTS = imports
