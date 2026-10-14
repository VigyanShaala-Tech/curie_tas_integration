"""Tests for CURIE defaults injected by the Django plugin."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from tas_app.settings.common import DEFAULT_CURIE_TRIGGER_URL, plugin_settings


class CuriePluginSettingsTest(SimpleTestCase):
    def test_aws_trigger_url_is_the_default(self):
        settings = SimpleNamespace()

        plugin_settings(settings)

        self.assertEqual(
            settings.CURIE_TRIGGER_URL,
            "http://13.204.198.16:3001/api/v1/assessment-reviews/",
        )
        self.assertEqual(settings.CURIE_TRIGGER_URL, DEFAULT_CURIE_TRIGGER_URL)

    def test_deployment_can_override_trigger_url(self):
        settings = SimpleNamespace(CURIE_TRIGGER_URL="https://curie.example/api/v1/assessment-reviews/")

        plugin_settings(settings)

        self.assertEqual(
            settings.CURIE_TRIGGER_URL,
            "https://curie.example/api/v1/assessment-reviews/",
        )
