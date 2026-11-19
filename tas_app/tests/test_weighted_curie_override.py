"""Weighted rubric grades for a failed CURIE review and a manual override."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from tas_app.curie.callback import apply_callback
from tas_app.models import CurieReview, InstructorFeedback, Rubric, Submission
from tas_app.tests.test_curie_manual_publish import MANUAL_SETTINGS
from tas_app.tests.test_curie_phase3 import _post_human_feedback
from tas_app.tests.test_curie_slice import _success_payload, _swot_submission
from tas_app.tests.test_models import UserFactory
from tas_app.utils.rubric_scoring import weighted_rubric_score


def _criteria(prefix):
    return [
        {
            "id": f"{prefix}-rel",
            "name": "Task Relevance",
            "indicators": [{"text": "Relevant", "marks": 10}],
        },
        {
            "id": f"{prefix}-rea",
            "name": "Reasoning / Understanding",
            "indicators": [{"text": "Reasoned", "marks": 10}],
        },
        {
            "id": f"{prefix}-spe",
            "name": "Specificity & Evidence",
            "indicators": [{"text": "Specific", "marks": 10}],
        },
    ]


def _component(component_id, name, weight, field_ids, is_gate=False):
    return {
        "id": component_id,
        "name": name,
        "learning_objective": "",
        "learning_outcome": "",
        "field_ids": field_ids,
        "weight": weight,
        "is_gate": is_gate,
        "criteria": _criteria(component_id),
        "feedbacks": [],
    }


SECTIONS = [
    {
        "id": "sec-gate",
        "title": "Basic Understanding",
        "components": [_component("gate", "Overall SWOT Coherence", 0, [], True)],
    },
    {
        "id": "sec-body",
        "title": "SWOT",
        "components": [
            _component("goal", "Goal", 50, ["goal"]),
            _component("strength", "Strengths", 50, ["strength"]),
        ],
    },
]


def _score_row(component_id, name, scores, comment):
    criteria = (
        ("rel", "Task Relevance"),
        ("rea", "Reasoning / Understanding"),
        ("spe", "Specificity & Evidence"),
    )
    return {
        "component_id": component_id,
        "component": name,
        "comment": comment,
        "criterion_scores": [
            {
                "criterion_id": f"{component_id}-{suffix}",
                "criterion": criterion,
                "score": score,
                "max_score": 10,
            }
            for (suffix, criterion), score in zip(criteria, scores)
        ],
    }


def _component_rows(goal_comment="Revise the timeframe."):
    return [
        _score_row("gate", "Overall SWOT Coherence", (7, 7, 7), "Gate note."),
        _score_row("goal", "Goal", (8, 6, 4), goal_comment),
        _score_row("strength", "Strengths", (10, 10, 10), "Strengths are evidenced."),
    ]


@override_settings(**MANUAL_SETTINGS)
class WeightedCurieOverrideTest(TestCase):
    def setUp(self):
        self.staff = UserFactory(is_staff=True, is_superuser=True)
        self.submission = _swot_submission(
            status=Submission.STATUS_SUBMITTED,
            version_number=2,
        )
        rubric = Rubric.objects.create(
            name="Weighted SWOT",
            schema_version=Rubric.SCHEMA_WEIGHTED,
            sections=SECTIONS,
            criteria=[],
        )
        block = self.submission.template_block
        block.rubric = rubric
        block.save(update_fields=["rubric", "modified"])
        self.review = CurieReview.objects.create(
            submission=self.submission,
            submission_version_number=2,
        )

    def _store_success(self):
        apply_callback(self.review, _success_payload(self.review))
        self.review.refresh_from_db()
        self.submission.refresh_from_db()

    def test_failed_review_saves_component_scores_and_section_feedback(self):
        self.review.status = CurieReview.STATUS_FAILED
        self.review.error_detail = "CURIE timed out."
        self.review.save(update_fields=["status", "error_detail", "modified"])

        with patch("tas_app.views._push_submission_grade"):
            response = _post_human_feedback(
                self.submission,
                self.staff,
                {
                    "status": "approved",
                    "comment": "Instructor overall.",
                    "rubrics": _component_rows(),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.submission.refresh_from_db()
        self.review.refresh_from_db()
        feedback = self.submission.feedback
        self.assertEqual(feedback.source, InstructorFeedback.SOURCE_HUMAN)
        self.assertEqual(feedback.comment, "Instructor overall.")
        self.assertEqual(feedback.rubrics[1]["comment"], "Revise the timeframe.")
        self.assertEqual(feedback.rubrics[1]["criterion_scores"][0]["score"], 8)
        self.assertEqual(weighted_rubric_score(feedback.rubrics, SECTIONS), (8.0, 10.0))
        self.assertEqual(feedback.structured_feedback, {})
        self.assertEqual(self.review.field_feedback, [])

    def test_override_replaces_projection_and_keeps_the_curie_review(self):
        self._store_success()
        original_goal = self.review.field_feedback[0]["comment"]
        original_gate = list(self.review.gate_criterion_scores)

        with patch("tas_app.views._push_submission_grade") as push_grade:
            response = _post_human_feedback(
                self.submission,
                self.staff,
                {
                    "status": "approved",
                    "comment": "<p>Instructor overall.</p>",
                    "rubrics": _component_rows(""),
                },
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.submission.refresh_from_db()
        self.review.refresh_from_db()
        feedback = self.submission.feedback
        self.assertEqual(feedback.source, InstructorFeedback.SOURCE_HUMAN)
        self.assertEqual(feedback.status, "approved")
        self.assertEqual(self.submission.status, Submission.STATUS_APPROVED)
        self.assertEqual(feedback.comment, "Instructor overall.")
        self.assertEqual(feedback.rubrics[1]["component_id"], "goal")
        self.assertEqual(feedback.rubrics[1]["comment"], "")
        self.assertEqual(weighted_rubric_score(feedback.rubrics, SECTIONS), (8.0, 10.0))
        push_grade.assert_called_once()
        self.assertEqual(push_grade.call_args[0][1], feedback.rubrics)

        structured = feedback.structured_feedback
        self.assertEqual(structured["verdict"], CurieReview.VERDICT_ACCEPTED)
        self.assertEqual(structured["overall_feedback"], "Instructor overall.")
        self.assertEqual(structured["gate_criterion_scores"][0]["score"], 7)
        by_field = {entry["field_id"]: entry for entry in structured["field_feedback"]}
        self.assertEqual(by_field["goal"]["comment"], "")
        self.assertEqual(by_field["goal"]["weight"], 1)
        self.assertEqual(by_field["goal"]["criterion_scores"][0]["score"], 8)
        self.assertEqual(by_field["goal"]["criterion_scores"][1]["score"], 6)
        self.assertEqual(by_field["strength"]["comment"], "Strengths are evidenced.")
        self.assertEqual(by_field["contribution"]["comment"], "Keep this reflection.")
        self.assertEqual(by_field["contribution"]["weight"], 0)

        self.review.refresh_from_db()
        self.assertEqual(self.review.status, CurieReview.STATUS_READY)
        self.assertEqual(self.review.field_feedback[0]["comment"], original_goal)
        self.assertEqual(self.review.gate_criterion_scores, original_gate)

    def test_ready_review_without_component_rows_still_requires_structured_feedback(self):
        self._store_success()
        response = _post_human_feedback(
            self.submission,
            self.staff,
            {"status": "rejected", "comment": "Old manual format.", "rubrics": []},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("structured_feedback", response.data)
        self.assertFalse(InstructorFeedback.objects.filter(submission=self.submission).exists())
