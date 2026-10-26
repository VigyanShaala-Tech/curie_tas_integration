from django.test import SimpleTestCase

from tas_app.serializers import TemplateSerializer


class TemplateStructureSerializerTest(SimpleTestCase):
    def test_legacy_fields_remain_valid_and_unchanged(self):
        fields = [{"id": "strength", "label": "Strengths", "type": "textarea", "weight": 1}]
        self.assertEqual(TemplateSerializer().validate_fields(fields), fields)

    def test_cards_table_stages_and_normal_text_are_valid(self):
        fields = [
            {"id": "name", "label": "Name & College", "type": "text", "maxChars": 80},
            {
                "id": "career",
                "section": "Career Exploration",
                "displayStyle": "table",
                "tableRow": "Option 1",
                "tableColumn": "Career",
            },
            {
                "id": "skills",
                "section": "Career Exploration",
                "displayStyle": "table",
                "tableRow": "Option 1",
                "tableColumn": "Skills",
            },
            {
                "id": "action",
                "section": "Career Progression",
                "displayStyle": "stages",
                "stage": "Explore",
                "stageOrder": 1,
            },
        ]
        self.assertEqual(TemplateSerializer().validate_fields(fields), fields)

    def test_instruction_and_guidance_are_preserved(self):
        fields = [
            {
                "id": "impact",
                "section": "Career impact",
                "sectionInstruction": "Think about people and communities.",
                "guidance": "Explain who benefits and how.",
            }
        ]
        self.assertEqual(TemplateSerializer().validate_fields(fields), fields)

    def test_instruction_and_guidance_must_be_text(self):
        with self.assertRaisesMessage(Exception, "sectionInstruction must be text"):
            TemplateSerializer().validate_fields([{"id": "impact", "sectionInstruction": []}])
        with self.assertRaisesMessage(Exception, "guidance must be text"):
            TemplateSerializer().validate_fields([{"id": "impact", "guidance": 4}])

    def test_table_requires_row_and_column(self):
        with self.assertRaisesMessage(Exception, "needs tableRow and tableColumn"):
            TemplateSerializer().validate_fields([{"id": "career", "displayStyle": "table"}])

    def test_stage_requires_name_and_positive_order(self):
        with self.assertRaisesMessage(Exception, "needs stage and a positive stageOrder"):
            TemplateSerializer().validate_fields(
                [{"id": "step", "displayStyle": "stages", "stage": "Explore", "stageOrder": 0}]
            )

    def test_named_section_has_one_display_style(self):
        with self.assertRaisesMessage(Exception, "must use one displayStyle"):
            TemplateSerializer().validate_fields(
                [
                    {"id": "a", "section": "Plan", "displayStyle": "cards"},
                    {
                        "id": "b",
                        "section": "Plan",
                        "displayStyle": "table",
                        "tableRow": "1",
                        "tableColumn": "B",
                    },
                ]
            )
