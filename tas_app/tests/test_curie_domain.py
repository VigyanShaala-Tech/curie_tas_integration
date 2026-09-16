"""Pure CURIE domain tests. These do not hit the network."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings

from tas_app.curie.constants import (
    FIELD_COLOR_COULD_IMPROVE,
    FIELD_COLOR_GOOD,
    FIELD_COLOR_NEEDS_REVISION,
    SOURCE_CURIE,
    SOURCE_HUMAN,
    STATUS_FAILED,
    STATUS_PENDING_EVALUATION,
    TIMEOUT_ERROR_DETAIL,
    VERDICT_ACCEPTED,
    VERDICT_REJECTED,
)
from tas_app.curie.scoring import compute_verdict, field_color_for_score, instructor_rubric_entries, star_rating
from tas_app.curie.settings import CurieSettingsError, validate_curie_settings
from tas_app.curie.timeout import is_slow_pending, resolve_timeout
from tas_app.curie.transitions import (
    can_apply_curie_projection,
    can_withdraw_feedback,
    human_owns_projection,
    is_at_attempt_cap,
    is_curie_eligible,
    legal_curie_resubmit,
)
from tas_app.curie.validation import CallbackValidationError, validate_callback_payload
from tas_app.curie.projection import sanitize_overall_feedback


def _scores(values):
    names = ("Task Relevance", "Reasoning / Understanding", "Specificity & Evidence")
    return [{"criterion": name, "score": value, "max_score": 10} for name, value in zip(names, values)]


def _field(field_id, values, weight=1):
    return {
        "field_id": field_id,
        "weight": weight,
        "comment": f"{field_id} comment",
        "criterion_scores": [] if weight == 0 else _scores(values),
    }


class CurieScoringTest(SimpleTestCase):
    def test_boundary_scores_accept_at_six(self):
        gate = _scores((9, 8, 9))
        fields = [
            _field("goal", (6, 6, 6)),
            _field("strength", (8, 8, 8)),
            _field("contribution", (0, 0, 0), weight=0),
        ]
        self.assertEqual(compute_verdict(gate, fields, threshold=6.0), VERDICT_ACCEPTED)

    def test_score_just_below_six_rejects(self):
        gate = _scores((9, 8, 9))
        fields = [_field("goal", (5, 6, 6)), _field("contribution", (), weight=0)]
        self.assertEqual(compute_verdict(gate, fields, threshold=6.0), VERDICT_REJECTED)

    def test_gate_failure_with_empty_fields_rejects(self):
        self.assertEqual(compute_verdict(_scores((3, 2, 4)), [], threshold=6.0), VERDICT_REJECTED)

    def test_weight_zero_field_does_not_change_verdict_or_stars(self):
        fields = [
            _field("goal", (9, 9, 9)),
            _field("contribution", (), weight=0),
        ]
        self.assertEqual(compute_verdict(_scores((9, 9, 9)), fields, threshold=6.0), VERDICT_ACCEPTED)
        self.assertEqual(star_rating(fields), 5)
        self.assertEqual(field_color_for_score(None), None)

    def test_colour_bands_use_exact_boundaries(self):
        self.assertEqual(field_color_for_score(5.99), FIELD_COLOR_NEEDS_REVISION)
        self.assertEqual(field_color_for_score(6.0), FIELD_COLOR_COULD_IMPROVE)
        self.assertEqual(field_color_for_score(7.67), FIELD_COLOR_COULD_IMPROVE)
        self.assertEqual(field_color_for_score(8.0), FIELD_COLOR_GOOD)

    def test_star_rating_is_whole_stars(self):
        fields = [_field("goal", (7, 7, 7))]
        self.assertEqual(star_rating(fields), 4)

    def test_gate_failure_has_no_star_rating(self):
        self.assertIsNone(star_rating([]))

    def test_instructor_rubrics_use_tas_category_names_and_marks(self):
        entries = instructor_rubric_entries([_field("goal", (9, 8, 7))])
        self.assertEqual(
            [entry["criterion"] for entry in entries],
            ["Task Relevance", "Reasoning/Understanding", "Specificity/Evidence"],
        )
        self.assertEqual(entries[0]["marks"], 9)
        self.assertIn("selected_option", entries[0])


class CurieValidationTest(SimpleTestCase):
    def test_success_payload_normalizes(self):
        payload = {
            "trigger_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "user_id": "48213",
            "submission_id": "4521",
            "submission_version_number": 2,
            "result": "success",
            "gate_criterion_scores": _scores((9, 8, 9)),
            "field_feedback": [_field("goal", (9, 8, 9)), _field("contribution", (), weight=0)],
            "overall_feedback": "Strong work.",
        }
        normalized = validate_callback_payload(payload, allowed_field_ids=["goal", "contribution"])
        self.assertEqual(normalized["result"], "success")

    def test_unknown_criterion_is_rejected(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "success",
            "gate_criterion_scores": [
                {"criterion": "Task Relevance", "score": 9, "max_score": 10},
                {"criterion": "Reasoning/Understanding", "score": 8, "max_score": 10},
                {"criterion": "Specificity & Evidence", "score": 9, "max_score": 10},
            ],
            "field_feedback": [],
            "overall_feedback": "Gate failed.",
        }
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload)

    def test_error_payload_requires_message(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "error",
        }
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload)

    def test_weight_zero_with_scores_is_rejected(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "success",
            "gate_criterion_scores": _scores((9, 8, 9)),
            "field_feedback": [
                {
                    "field_id": "contribution",
                    "weight": 0,
                    "comment": "comment",
                    "criterion_scores": _scores((9, 9, 9)),
                }
            ],
            "overall_feedback": "ok",
        }
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload)


class CurieReviewRegressionTest(SimpleTestCase):
    """Focused coverage for the seven Phase 1 review corrections."""

    def test_passing_gate_requires_every_submitted_field(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "success",
            "gate_criterion_scores": _scores((9, 8, 9)),
            "field_feedback": [_field("goal", (9, 8, 9))],
            "overall_feedback": "ok",
        }
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload, allowed_field_ids=["goal", "contribution"])

    def test_failing_gate_rejects_non_empty_field_feedback(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "success",
            "gate_criterion_scores": _scores((3, 2, 4)),
            "field_feedback": [_field("goal", (9, 8, 9))],
            "overall_feedback": "Gate failed.",
        }
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload, allowed_field_ids=["goal"])

    def test_failing_gate_accepts_empty_field_feedback(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "success",
            "gate_criterion_scores": _scores((3, 2, 4)),
            "field_feedback": [],
            "overall_feedback": "Gate failed.",
        }
        normalized = validate_callback_payload(payload, allowed_field_ids=["goal"])
        self.assertEqual(normalized["field_feedback"], [])

    def test_human_ownership_survives_withdraw_to_pending(self):
        self.assertTrue(human_owns_projection(SOURCE_HUMAN, "pending"))
        self.assertFalse(
            can_apply_curie_projection(
                review_status=STATUS_FAILED,
                callback_version=3,
                current_version=3,
                feedback_source=SOURCE_HUMAN,
                feedback_status="pending",
            )
        )
        self.assertFalse(can_withdraw_feedback(SOURCE_CURIE))
        self.assertTrue(can_withdraw_feedback(SOURCE_HUMAN))

    def test_verdict_uses_configured_pass_threshold(self):
        gate = _scores((9, 8, 9))
        fields = [_field("goal", (6, 6, 6))]
        self.assertEqual(compute_verdict(gate, fields, threshold=6.0), VERDICT_ACCEPTED)
        self.assertEqual(compute_verdict(gate, fields, threshold=7.0), VERDICT_REJECTED)

    def test_non_finite_or_wrong_scale_scores_are_rejected(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "success",
            "gate_criterion_scores": [
                {"criterion": "Task Relevance", "score": 9, "max_score": 10},
                {"criterion": "Reasoning / Understanding", "score": float("nan"), "max_score": 10},
                {"criterion": "Specificity & Evidence", "score": 9, "max_score": 10},
            ],
            "field_feedback": [],
            "overall_feedback": "ok",
        }
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload)
        payload["gate_criterion_scores"] = [
            {"criterion": "Task Relevance", "score": float("inf"), "max_score": 10},
            {"criterion": "Reasoning / Understanding", "score": 8, "max_score": 10},
            {"criterion": "Specificity & Evidence", "score": 9, "max_score": 10},
        ]
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload)
        payload["gate_criterion_scores"] = [
            {"criterion": "Task Relevance", "score": 50, "max_score": 100},
            {"criterion": "Reasoning / Understanding", "score": 50, "max_score": 100},
            {"criterion": "Specificity & Evidence", "score": 50, "max_score": 100},
        ]
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload)
        payload["gate_criterion_scores"] = [
            {"criterion": "Task Relevance", "score": True, "max_score": 10},
            {"criterion": "Reasoning / Understanding", "score": 8, "max_score": 10},
            {"criterion": "Specificity & Evidence", "score": 9, "max_score": 10},
        ]
        with self.assertRaises(CallbackValidationError):
            validate_callback_payload(payload)

    def test_submission_version_must_be_positive_json_integer(self):
        base = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "result": "error",
            "error_message": "broken",
        }
        for value in (2.0, True, "2", 0, -1):
            with self.assertRaises(CallbackValidationError):
                validate_callback_payload({**base, "submission_version_number": value})
        self.assertEqual(
            validate_callback_payload({**base, "submission_version_number": 2})["submission_version_number"],
            2,
        )

    def test_field_weight_must_be_integer_zero_or_one(self):
        payload = {
            "trigger_id": "t",
            "user_id": "1",
            "submission_id": "2",
            "submission_version_number": 1,
            "result": "success",
            "gate_criterion_scores": _scores((9, 8, 9)),
            "overall_feedback": "ok",
        }
        for weight in (1.0, True, "1", 2):
            payload["field_feedback"] = [
                {
                    "field_id": "goal",
                    "weight": weight,
                    "comment": "comment",
                    "criterion_scores": _scores((9, 8, 9)),
                }
            ]
            with self.assertRaises(CallbackValidationError):
                validate_callback_payload(payload)

    @override_settings(
        CURIE_ENABLED=True,
        CURIE_TRIGGER_URL="https://curie.example/api/v1/assessment-reviews/",
        CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret",
        CURIE_SHARED_SECRET="secret",
        CURIE_CONNECT_TIMEOUT_SECONDS=3,
        CURIE_REQUEST_TIMEOUT_SECONDS=10,
        CURIE_REVIEW_TIMEOUT_SECONDS=300,
        CURIE_REVIEW_MAX_WAIT_SECONDS=1800,
        CURIE_COMPONENT_PASS_THRESHOLD=6.0,
    )
    def test_enabled_settings_accept_a_complete_contract(self):
        validate_curie_settings()

    @override_settings(
        CURIE_ENABLED=True,
        CURIE_TRIGGER_URL="not-a-url",
        CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret",
        CURIE_SHARED_SECRET="secret",
    )
    def test_enabled_settings_reject_malformed_url(self):
        with self.assertRaises(CurieSettingsError):
            validate_curie_settings()

    @override_settings(
        CURIE_ENABLED=True,
        CURIE_TRIGGER_URL="https://curie.example/api/v1/assessment-reviews/",
        CURIE_AUTH_HEADER_NAME="X Curie",
        CURIE_SHARED_SECRET="secret",
    )
    def test_enabled_settings_reject_invalid_header_name(self):
        with self.assertRaises(CurieSettingsError):
            validate_curie_settings()

    @override_settings(
        CURIE_ENABLED=True,
        CURIE_TRIGGER_URL="https://curie.example/api/v1/assessment-reviews/",
        CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret",
        CURIE_SHARED_SECRET="   ",
    )
    def test_enabled_settings_reject_blank_secret(self):
        with self.assertRaises(CurieSettingsError):
            validate_curie_settings()

    @override_settings(
        CURIE_ENABLED=True,
        CURIE_TRIGGER_URL="https://curie.example/api/v1/assessment-reviews/",
        CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret",
        CURIE_SHARED_SECRET="secret",
        CURIE_CONNECT_TIMEOUT_SECONDS=0,
        CURIE_REQUEST_TIMEOUT_SECONDS=10,
        CURIE_REVIEW_TIMEOUT_SECONDS=300,
        CURIE_REVIEW_MAX_WAIT_SECONDS=1800,
        CURIE_COMPONENT_PASS_THRESHOLD=6.0,
    )
    def test_enabled_settings_reject_non_positive_timeout(self):
        with self.assertRaises(CurieSettingsError):
            validate_curie_settings()

    @override_settings(
        CURIE_ENABLED=True,
        CURIE_TRIGGER_URL="https://curie.example/api/v1/assessment-reviews/",
        CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret",
        CURIE_SHARED_SECRET="secret",
        CURIE_CONNECT_TIMEOUT_SECONDS=3,
        CURIE_REQUEST_TIMEOUT_SECONDS=10,
        CURIE_REVIEW_TIMEOUT_SECONDS=1800,
        CURIE_REVIEW_MAX_WAIT_SECONDS=300,
        CURIE_COMPONENT_PASS_THRESHOLD=6.0,
    )
    def test_enabled_settings_reject_slow_after_max_wait(self):
        with self.assertRaises(CurieSettingsError):
            validate_curie_settings()

    @override_settings(
        CURIE_ENABLED=True,
        CURIE_TRIGGER_URL="https://curie.example/api/v1/assessment-reviews/",
        CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret",
        CURIE_SHARED_SECRET="secret",
        CURIE_CONNECT_TIMEOUT_SECONDS=3,
        CURIE_REQUEST_TIMEOUT_SECONDS=10,
        CURIE_REVIEW_TIMEOUT_SECONDS=300,
        CURIE_REVIEW_MAX_WAIT_SECONDS=1800,
        CURIE_COMPONENT_PASS_THRESHOLD=11,
    )
    def test_enabled_settings_reject_threshold_outside_zero_to_ten(self):
        with self.assertRaises(CurieSettingsError):
            validate_curie_settings()


class CurieTransitionTest(SimpleTestCase):
    def test_eligibility_requires_both_flags_and_swot(self):
        self.assertFalse(is_curie_eligible(global_enabled=True, block_enabled=False, assignment_type="swot"))
        self.assertFalse(is_curie_eligible(global_enabled=True, block_enabled=True, assignment_type="resume"))
        self.assertTrue(is_curie_eligible(global_enabled=True, block_enabled=True, assignment_type="swot"))

    def test_failed_reviews_do_not_consume_cap(self):
        reviews = [MagicMock(status=STATUS_FAILED)] * 10
        self.assertFalse(is_at_attempt_cap(reviews))

    def test_approved_is_never_a_legal_resubmit_source(self):
        self.assertFalse(
            legal_curie_resubmit(
                submission_status="approved",
                review_status="ready",
                feedback_source=SOURCE_CURIE,
            )
        )

    def test_first_draft_with_no_feedback_is_legal(self):
        self.assertTrue(
            legal_curie_resubmit(
                submission_status="draft",
                review_status=None,
                feedback_source=None,
            )
        )

    def test_human_ownership_blocks_draft_and_failed_submit(self):
        self.assertFalse(
            legal_curie_resubmit(
                submission_status="draft",
                review_status=None,
                feedback_source=SOURCE_HUMAN,
            )
        )
        self.assertFalse(
            legal_curie_resubmit(
                submission_status="submitted",
                review_status=STATUS_FAILED,
                feedback_source=SOURCE_HUMAN,
            )
        )

    def test_human_precedence_blocks_projection(self):
        self.assertTrue(human_owns_projection(SOURCE_HUMAN, "approved"))
        self.assertFalse(
            can_apply_curie_projection(
                review_status=STATUS_PENDING_EVALUATION,
                callback_version=3,
                current_version=3,
                feedback_source=SOURCE_HUMAN,
                feedback_status="approved",
            )
        )


class CurieTimeoutTest(SimpleTestCase):
    def test_five_minutes_is_slow_but_not_failed(self):
        requested = datetime(2026, 9, 12, tzinfo=timezone.utc)
        now = requested + timedelta(seconds=300)
        self.assertTrue(is_slow_pending(requested, now))
        review = MagicMock(status=STATUS_PENDING_EVALUATION, requested_at=requested, error_detail="")
        resolve_timeout(review, now)
        self.assertEqual(review.status, STATUS_PENDING_EVALUATION)

    def test_thirty_minutes_marks_failed_idempotently(self):
        requested = datetime(2026, 9, 12, tzinfo=timezone.utc)
        now = requested + timedelta(seconds=1800)
        review = MagicMock(status=STATUS_PENDING_EVALUATION, requested_at=requested, error_detail="")
        resolve_timeout(review, now)
        self.assertEqual(review.status, STATUS_FAILED)
        self.assertEqual(review.error_detail, TIMEOUT_ERROR_DETAIL)
        resolve_timeout(review, now + timedelta(minutes=1))
        self.assertEqual(review.status, STATUS_FAILED)


class CurieSettingsTest(SimpleTestCase):
    @override_settings(CURIE_ENABLED=False, CURIE_TRIGGER_URL="", CURIE_AUTH_HEADER_NAME="", CURIE_SHARED_SECRET="")
    def test_disabled_curie_does_not_require_wire_settings(self):
        validate_curie_settings()

    @override_settings(CURIE_ENABLED=True, CURIE_TRIGGER_URL="", CURIE_AUTH_HEADER_NAME="X-Curie-Shared-Secret", CURIE_SHARED_SECRET="secret")
    def test_enabled_curie_requires_trigger_url(self):
        with self.assertRaises(CurieSettingsError):
            validate_curie_settings()


class CurieProjectionSanitizeTest(SimpleTestCase):
    def test_colon_ending_headings_are_stripped(self):
        text = "What to improve:\nKeep the goal time-bound."
        self.assertEqual(sanitize_overall_feedback(text), "Keep the goal time-bound.")
