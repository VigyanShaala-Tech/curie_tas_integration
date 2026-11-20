"""
Tests for weighted (schema_version 2) rubrics in ``tas_app.utils.rubric_scoring``.
"""

from django.test import SimpleTestCase

from tas_app.utils.rubric_scoring import (
    SCHEMA_WEIGHTED,
    component_score,
    score_rubric,
    validate_rubric_sections,
    weighted_rubric_score,
)


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
        """Verifies scores match by criterion name, clamp to 10, and missing criteria count as 0."""
        component = _component("strengths", 50)
        row = {"criterion_scores": [{"criterion": "Task Relevance", "score": 15}, {"criterion": "Other", "score": 1}]}
        self.assertAlmostEqual(component_score(component, row), 10 / 3)
        self.assertIsNone(component_score(component, {"criterion_scores": []}))

    def test_empty_feedback_keeps_weighted_max(self):
        """Verifies a weighted rubric with no rows is 0 earned out of 10."""
        self.assertEqual(score_rubric(SCHEMA_WEIGHTED, [], SECTIONS, []), (0.0, 10.0))

    def test_curie_category_rows_use_field_feedback(self):
        """Verifies CURIE's three category rows still score when field_feedback maps to components."""
        strengths = _component("strengths", 50)
        strengths["field_ids"] = ["strength"]
        plans = _component("plans", 50)
        plans["field_ids"] = ["action_plans"]
        sections = [
            {"id": "gate", "title": "Basic Understanding", "components": [_component("coherence", 0, is_gate=True)]},
            {"id": "quadrants", "title": "SWOT Quadrants", "components": [strengths, plans]},
        ]
        category_rows = [
            {"criterion": "Task Relevance", "marks": 9, "selected_option": "Score: 9"},
            {"criterion": "Reasoning/Understanding", "marks": 8, "selected_option": "Score: 8"},
            {"criterion": "Specificity/Evidence", "marks": 9, "selected_option": "Score: 9"},
        ]
        field_feedback = [
            {
                "field_id": "strength",
                "weight": 1,
                "criterion_scores": [
                    {"criterion": "Task Relevance", "score": 8},
                    {"criterion": "Reasoning / Understanding", "score": 7},
                    {"criterion": "Specificity & Evidence", "score": 6},
                ],
            },
            {
                "field_id": "action_plans",
                "weight": 1,
                "criterion_scores": [
                    {"criterion": "Task Relevance", "score": 10},
                    {"criterion": "Reasoning / Understanding", "score": 10},
                    {"criterion": "Specificity & Evidence", "score": 10},
                ],
            },
        ]
        self.assertEqual(
            score_rubric(SCHEMA_WEIGHTED, [], sections, category_rows, field_feedback=field_feedback),
            (8.5, 10.0),
        )
        self.assertEqual(
            score_rubric(SCHEMA_WEIGHTED, [], sections, category_rows),
            (0.0, 10.0),
        )

    def test_swot_success_payload_is_not_zero_out_of_ten(self):
        """Verifies CURIE SWOT field_feedback (goal/strength 50% each) scores 8.67/10, not 0/10."""
        goal = _component("goal", 50)
        goal["field_ids"] = ["goal"]
        strength = _component("strength", 50)
        strength["field_ids"] = ["strength"]
        sections = [
            {"id": "sec-gate", "title": "Gate", "components": [_component("gate", 0, is_gate=True)]},
            {"id": "sec-body", "title": "SWOT", "components": [goal, strength]},
        ]
        criterion_scores = [
            {"criterion": "Task Relevance", "score": 9},
            {"criterion": "Reasoning / Understanding", "score": 8},
            {"criterion": "Specificity & Evidence", "score": 9},
        ]
        field_feedback = [
            {"field_id": "goal", "weight": 1, "criterion_scores": criterion_scores},
            {"field_id": "strength", "weight": 1, "criterion_scores": criterion_scores},
            {"field_id": "contribution", "weight": 0, "criterion_scores": criterion_scores},
        ]
        category_rows = [
            {"criterion": "Task Relevance", "marks": 9, "selected_option": "Score: 9"},
        ]
        self.assertEqual(
            score_rubric(SCHEMA_WEIGHTED, [], sections, category_rows, field_feedback=field_feedback),
            (8.67, 10.0),
        )
