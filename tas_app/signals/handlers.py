from django.dispatch import receiver
from xmodule.modulestore.django import SignalHandler
from tas_app.models import TemplateBlock, Submission, SubmissionVersion, InstructorFeedback


@receiver(SignalHandler.item_deleted)
def delete_tas_data_on_unit_delete(**kwargs):
    usage_key = kwargs.get("usage_key")

    if not usage_key:
        return

    block_id = str(usage_key)
    print("TAS DELETE TRIGGERED:", block_id)

    try:
        # 1. Delete Instructor Feedback (via submission)
        submissions = Submission.objects.filter(usage_key=block_id)

        for sub in submissions:
            InstructorFeedback.objects.filter(submission=sub).delete()
            SubmissionVersion.objects.filter(submission=sub).delete()

        # 2. Delete Submissions
        submissions.delete()

        # 3. Delete TemplateBlock
        TemplateBlock.objects.filter(usage_key=block_id).delete()

        print("TAS DATA DELETED SUCCESSFULLY")

    except Exception as e:
        print("TAS DELETE ERROR:", str(e))
