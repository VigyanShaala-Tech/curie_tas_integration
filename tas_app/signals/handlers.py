import logging

from django.dispatch import receiver
from xmodule.modulestore.django import SignalHandler
from tas_app.models import TemplateBlock, Submission, SubmissionVersion, InstructorFeedback

log = logging.getLogger(__name__)


@receiver(SignalHandler.item_deleted)
def delete_tas_data_on_unit_delete(**kwargs):
    usage_key = kwargs.get("usage_key")

    if not usage_key:
        return

    block_id = str(usage_key)
    log.info("TAS delete triggered for usage_key=%s", block_id)

    try:
        submissions = Submission.objects.filter(usage_key=block_id)
        submission_ids = list(submissions.values_list("id", flat=True))
        InstructorFeedback.objects.filter(submission_id__in=submission_ids).delete()
        SubmissionVersion.objects.filter(submission_id__in=submission_ids).delete()
        submissions.delete()
        TemplateBlock.objects.filter(usage_key=block_id).delete()
        log.info("TAS data deleted for usage_key=%s", block_id)
    except Exception:  # pylint: disable=broad-except
        log.exception("TAS delete failed for usage_key=%s", block_id)
