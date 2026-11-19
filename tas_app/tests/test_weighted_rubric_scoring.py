"""
Tests for weighted (schema_version 2) rubrics in ``tas_app.utils.rubric_scoring``.
"""

from django.test import SimpleTestCase

from tas_app.utils.rubric_scoring import component_score, validate_rubric_sections, weighted_rubric_score


def _criterion(cid, name, marks=(10,)):
    return {
        "id": cid,
        "name": name,
        "indicators": [{"text": f"{name} {i}", "marks": m} for i, m in enumerate(marks)],
    }


def _component(cid, weight, is_gate=False):
    return {
        "id": cid,
        "name": cid.title(),
        "learning_objective": "",
        "learning_outcome": "",
        "field_ids": [],
        "weight": weight,
        "is_gate": is_gate,
        "criteria": [
            _criterion(f"{cid}-rel", "Task Relevance", (4, 3, 3)),
            _criterion(f"{cid}-rea", "Reasoning / Understanding", (5, 5)),
            _criterion(f"{cid}-spe", "Specificity & Evidence"),
        ],
    }


SECTIONS = [
    {"id": "gate", "title": "Basic Understanding", "components": [_component("coherence", 0, is_gate=True)]},
    {
        "id": "quadrants",
        "title": "SWOT Quadrants",
        "components": [_component("strengths", 50), _component("plans", 50)],
    },
]


def _row(cid, scores):
    return {
        "component_id": cid,
        "criterion_scores": [
            {"criterion_id": f"{cid}-{key}", "score": score} for key, score in zip(("rel", "rea", "spe"), scores)
        ],
    }


class ValidateRubricSectionsTest(SimpleTestCase):
    def test_valid_rubric(self):
        """Verifies a rubric with 10-mark criteria and 100% weight has no problems."""
        self.assertEqual(validate_rubric_sections(SECTIONS), [])

    def test_reports_weight_total_and_marks(self):
        """Verifies wrong weight totals, gate weights and indicator totals are reported."""
        sections = [
            {
                "id": "s",
                "title": "S",
                "components": [_component("a", 40), _component("g", 5, is_gate=True)],
            }
        ]
        sections[0]["components"][0]["criteria"][0]["indicators"][0]["marks"] = 1
        errors = validate_rubric_sections(sections)
        self.assertTrue(any("add up to 100%" in e for e in errors))
        self.assertTrue(any("gate component must have 0% weight" in e for e in errors))
        self.assertTrue(any("add up to 10 (now 7)" in e for e in errors))

    def test_empty(self):
        """Verifies an empty rubric is rejected."""
        self.assertEqual(validate_rubric_sections([]), ["Add at least one section."])


class WeightedRubricScoreTest(SimpleTestCase):
    def test_scoring_logic_example(self):
        """Verifies the Excel 'Scoring Logic': average the criteria, then apply the weight."""
        rubrics = [_row("strengths", (8, 7, 6)), _row("plans", (10, 10, 10)), _row("coherence", (0, 0, 0))]
        # strengths: avg 7 -> 5 marks * 0.7 = 3.5; plans: 5 marks; gate adds nothing.
        self.assertEqual(weighted_rubric_score(rubrics, SECTIONS), (8.5, 10.0))

    def test_unscored_components_earn_nothing(self):
        """Verifies components without feedback count 0 toward a 10-mark maximum."""
        self.assertEqual(weighted_rubric_score([], SECTIONS), (0.0, 10.0))

    def test_ignores_legacy_and_field_rows(self):
        """Verifies rows without component_id are not counted."""
        rubrics = [
            {"criterion": "Task Relevance", "marks": 10},
            {"field_id": "f-1", "criterion_scores": [{"criterion": "Task Relevance", "score": 9}]},
        ]
        self.assertEqual(weighted_rubric_score(rubrics, SECTIONS), (0.0, 10.0))

    def test_component_score_matches_name_and_clamps(self):
        """Verifies scores match by criterion name when ids changed, and stay within 0-10."""
        component = _component("strengths", 50)
        row = {"criterion_scores": [{"criterion": "Task Relevance", "score": 15}, {"criterion": "Other", "score": 1}]}
        self.assertEqual(component_score(component, row), 10)
        self.assertIsNone(component_score(component, {"criterion_scores": []}))
