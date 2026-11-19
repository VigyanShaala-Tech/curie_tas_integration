"""
Tests for rubric maximum marks (``tas_app.utils.rubric_scoring``) and ``views._calculate_score``.
"""

from django.test import SimpleTestCase

from tas_app.utils.rubric_scoring import criterion_max_marks, rubric_max_marks
from tas_app.views import _calculate_score, ordered_template_field_labels

# "Career exploration" rubric: three criteria whose options add up to 10 each.
CRITERIA = [
    {"criterion": "Task Relevance", "options": [{"name": f"T{i}", "marks": m} for i, m in enumerate([2, 2, 3, 2, 1])]},
    {"criterion": "Reasoning", "options": [{"name": f"R{i}", "marks": m} for i, m in enumerate([1, 3, 2, 3, 1])]},
    {"criterion": "Specificity", "options": [{"name": f"S{i}", "marks": m} for i, m in enumerate([2, 3, 2, 2, 1])]},
]


class RubricMaxMarksTest(SimpleTestCase):
    """A criterion is worth the sum of its option marks, a rubric the sum over its criteria."""

    def test_sum_of_option_marks(self):
        """Verifies three criteria of 10 make a 30-mark rubric, not the highest option per criterion (9)."""
        self.assertEqual(criterion_max_marks(CRITERIA[0]["options"]), 10)
        self.assertEqual(rubric_max_marks(CRITERIA), 30)

    def test_empty(self):
        """Verifies a rubric without criteria or options is worth nothing."""
        self.assertEqual(rubric_max_marks(None), 0)
        self.assertEqual(rubric_max_marks([{"criterion": "Empty", "options": []}]), 0)


class CalculateScoreTest(SimpleTestCase):
    """``_calculate_score`` returns marks given by the grading screen out of the rubric's total."""

    def test_grading_screen_scores(self):
        """Verifies "Score: N" entries (one 0-10 score per criterion) count their marks out of 30."""
        rubrics = [
            {"criterion": "Task Relevance", "selected_option": "Score: 10", "marks": 10},
            {"criterion": "Reasoning", "selected_option": "Score: 8", "marks": 8},
            {"criterion": "Specificity", "selected_option": "Score: 5", "marks": 5},
        ]
        self.assertEqual(_calculate_score(rubrics, CRITERIA), (23, 30))

    def test_field_rows_do_not_add_marks(self):
        """Per-template-field evaluation rows stay out of the rubric total."""
        rubrics = [
            {"criterion": "Task Relevance", "selected_option": "Score: 10", "marks": 10},
            {
                "field_id": "f-1",
                "comment": "section note",
                "criterion_scores": [{"criterion": "Task Relevance", "score": 4}],
                "marks": 99,
            },
        ]
        self.assertEqual(_calculate_score(rubrics, CRITERIA), (10, 30))

    def test_component_rows_do_not_add_marks(self):
        """Weighted-component rows stay out of a simple rubric's total."""
        rubrics = [
            {"criterion": "Reasoning", "selected_option": "Score: 8", "marks": 8},
            {"component_id": "c-1", "criterion_scores": [{"criterion_id": "k", "score": 9}], "marks": 99},
        ]
        self.assertEqual(_calculate_score(rubrics, CRITERIA), (8, 30))


class OrderedTemplateFieldLabelsTest(SimpleTestCase):
    """Submission detail lists active template fields once, in stored order."""

    def test_skips_inactive_and_duplicate_ids(self):
        fields = [
            {"id": "f-gate", "label": "Overall SWOT Coherence & Alignment"},
            {"id": "f-hidden", "label": "Hidden", "active": False},
            {"id": "f-plans", "label": "3 Action Plans"},
            {"id": "f-gate", "label": "Renamed later"},
            {"id": "", "label": "Missing id"},
            "not-a-field",
        ]
        self.assertEqual(
            list(ordered_template_field_labels(fields).items()),
            [
                ("f-gate", "Overall SWOT Coherence & Alignment"),
                ("f-plans", "3 Action Plans"),
            ],
        )
