"""CURIE defaults for assignments created through the TAS Studio XBlock."""

from django.test import TestCase
from opaque_keys.edx.keys import CourseKey, UsageKey

from tas_app.tests.test_models import TemplateBlockFactory, TemplateFactory, TemplateTypeFactory, UserFactory
from tas_xblock.tas import _upsert_template_block


class StudioCurieEnablementTest(TestCase):
    def setUp(self):
        self.user = UserFactory()
        self.course_key = CourseKey.from_string("course-v1:edX+DemoX+2026_T1")

    def _upsert(self, *, template, block_id):
        return _upsert_template_block(
            usage_key=UsageKey.from_string(f"block-v1:edX+DemoX+2026_T1+type@tas+block@{block_id}"),
            course_key=self.course_key,
            template=template,
            display_name="Template Based Assignment",
            instructions="Complete the assignment.",
            rubric=None,
            assigned_by=self.user,
        )

    def test_new_swot_assignment_enables_curie(self):
        template = TemplateFactory(template_type=TemplateTypeFactory(name="SWOT", slug="swot"))

        block = self._upsert(template=template, block_id="new-swot")

        self.assertTrue(block.curie_enabled)

    def test_new_non_swot_assignment_keeps_curie_disabled(self):
        template = TemplateFactory(template_type=TemplateTypeFactory(name="Essay", slug="essay"))

        block = self._upsert(template=template, block_id="new-essay")

        self.assertFalse(block.curie_enabled)

    def test_studio_resave_preserves_manual_disable(self):
        template = TemplateFactory(template_type=TemplateTypeFactory(name="SWOT", slug="swot"))
        usage_key = UsageKey.from_string("block-v1:edX+DemoX+2026_T1+type@tas+block@existing-swot")
        existing = TemplateBlockFactory(
            template=template,
            usage_key=usage_key,
            course_key=self.course_key,
            curie_enabled=False,
        )

        block = self._upsert(template=template, block_id="existing-swot")

        self.assertEqual(block.pk, existing.pk)
        self.assertFalse(block.curie_enabled)
