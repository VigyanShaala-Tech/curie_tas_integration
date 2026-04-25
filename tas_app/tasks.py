from datetime import datetime
import logging

from celery import shared_task
from common.djangoapps.util.date_utils import to_timestamp
from django.contrib.auth.models import User
from opaque_keys.edx.keys import CourseKey, UsageKey
from lms.djangoapps.courseware.models import StudentModule
from lms.djangoapps.grades.tasks import recalculate_subsection_grade_v3
from lms.djangoapps.grades.constants import ScoreDatabaseTableEnum
from lms.djangoapps.grades.events import PROBLEM_SUBMITTED_EVENT_TYPE
from common.djangoapps.track.event_transaction_utils import set_event_transaction_type, create_new_event_transaction_id

log = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def push_grade_to_lms(self, usage_key_str, course_key_str, student_id, earned, max_possible):
    """
    Write earned/max_possible into StudentModule and trigger subsection grade
    recalculation so the LMS course gradebook reflects the change immediately.

    Called after an instructor approves a submission, and again whenever the
    linked Rubric's criteria marks are updated.

    Retried up to 3 times (30-second back-off) on any exception.
    """
    try:
        usage_key = UsageKey.from_string(usage_key_str)
        course_key = CourseKey.from_string(course_key_str)

        # Persist the raw grade so the gradebook has a record even if the
        # student has never opened the XBlock page themselves.
        student_module, created = StudentModule.objects.update_or_create(
            module_state_key=usage_key,
            student_id=student_id,
            course_id=course_key,
            defaults={
                "grade": earned,
                "max_grade": max_possible,
                "module_type": "problem",
            },
        )

        set_event_transaction_type(PROBLEM_SUBMITTED_EVENT_TYPE)
        # Ask the grades subsystem to propagate the new raw score up through
        # subsection and course totals.
        recalculate_subsection_grade_v3.apply_async(
            kwargs=dict(
                user_id=student_id,
                course_id=str(course_key),
                usage_id=str(usage_key),
                only_if_higher=False,
                score_deleted=False,
                score_db_table=ScoreDatabaseTableEnum.courseware_student_module,
                expected_modified_time=to_timestamp(student_module.modified),
                event_transaction_id=str(create_new_event_transaction_id()),
                event_transaction_type=PROBLEM_SUBMITTED_EVENT_TYPE,
            )
        )

        log.info(
            "Grade pushed to LMS: student_id=%s block=%s earned=%s/%s",
            student_id,
            usage_key_str,
            earned,
            max_possible,
        )

    except Exception as exc:
        log.exception(
            "Grade push failed: student_id=%s block=%s",
            student_id,
            usage_key_str,
        )
        raise self.retry(exc=exc)
