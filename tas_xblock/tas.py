"""TO-DO: Write a description of what this XBlock is."""

import os
from datetime import datetime

import pkg_resources
from django.template import Context
from django.conf import settings
from xblock.core import XBlock
from xblock.fields import Float, Scope, String
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader

from django.contrib.auth.models import User
from lms.djangoapps.courseware.access import has_access
from tas_app.models import TemplateBlock, Template, TemplateType, Submission, Rubric
from tas_app.utils.student_feedback import strip_category_headings_from_comment


def _(text):
    """
    Dummy ugettext.
    """
    return text


@XBlock.needs("i18n")  # pylint: disable=too-many-ancestors
class TASXBlock(XBlock):
    """
    TO-DO: document what your XBlock does.
    """

    # Fields are defined on the class.  You can access them in your code as
    # self.<fieldname>.

    loader = ResourceLoader(__name__)

    has_score = True
    icon_class = "problem"

    display_name = String(
        display_name=_("Display Name"),
        default=_("Template Based Assignment"),
        scope=Scope.settings,
        help=_(
            "This name appears in the horizontal navigation at the top of the page for the template based assignment."
        ),
    )
    template_type = String(
        display_name=_("Template Type"),
        scope=Scope.settings,
        help=_("Select type of the template to use for the template based assignment."),
    )

    template = String(
        display_name=_("Template"),
        scope=Scope.settings,
        help=_("Select the template to use for the template based assignment."),
    )

    instructions = String(
        display_name=_("Instructions"),
        scope=Scope.settings,
        default=_("This is a template based assignment. Click on the button below to submit the assignment."),
        help=_("Write instructions for the student to follow while submitting the assignment."),
    )

    rubric_id = String(
        display_name=_("Rubric"),
        scope=Scope.settings,
        default="",
        help=_("ID of the Rubric record from the library to use for grading this assignment."),
    )

    weight = Float(
        display_name=_("Problem Weight"),
        scope=Scope.settings,
        default=1.0,
        help=_("Defines the weight of this assignment when calculating the course grade."),
    )

    def load_resource(self, resource_path):  # pylint: disable=no-self-use
        """
        Gets the content of a resource
        """

        resource_content = pkg_resources.resource_string(__name__, resource_path)
        return resource_content.decode("utf-8")

    def render_template(self, path, context=None):
        """
        Evaluate a template by resource path, applying the provided context
        """

        return self.loader.render_django_template(
            os.path.join("static/html", path),
            context=Context(context or {}),
            i18n_service=self.runtime.service(self, "i18n"),
        )

    def get_assigment_status(self):
        """
        Get student assignment submission status and feedback (including rubric marks).
        """
        assigment_pdf_url = None
        feedback = None
        try:
            submission = Submission.objects.select_related("feedback").get(
                usage_key=self.location, student=self.runtime.get_real_user()
            )
            assigment_pdf_url = submission.pdf.url if submission.pdf else None
            try:
                fb = submission.feedback
                feedback = {
                    "status": fb.status,
                    "comment": fb.comment,
                    "comment_html": strip_category_headings_from_comment(fb.comment),
                    "rubrics": fb.rubrics or [],
                }
            except Exception:
                pass
        except Exception:
            return "not_submitted", None, None
        return submission.status, assigment_pdf_url, feedback

    def is_past_due(self):
        """
        Is it now past this assignment's due date (including grace period)?

        `due` and `graceperiod` are not fields declared on this XBlock -- they're
        standard Open edX fields (`xmodule.modulestore.inheritance.InheritanceMixin`)
        that every block picks up from the LMS/CMS runtime and that cascade down from
        an ancestor (e.g. the parent subsection) unless overridden lower in the tree.
        Reading `self.due` here therefore already reflects the effective, fully
        resolved due date -- including any per-student extension -- exactly as it does
        for the built-in problem block (see `xmodule/capa_block.py::close_date`).
        """
        due_date = self.due
        if due_date is None:
            return False
        if self.graceperiod:
            due_date = due_date + self.graceperiod
        return datetime.now(due_date.tzinfo) > due_date

    def max_score(self):
        """
        Return the maximum achievable score across all rubric criteria.

        Fetches criteria from the linked Rubric record. Returns None when no
        rubric is selected or the record is missing, so the runtime treats this
        block as ungraded.
        """
        if not self.rubric_id:
            return None
        try:
            rubric = Rubric.objects.get(pk=self.rubric_id, is_active=True)
        except (Rubric.DoesNotExist, ValueError):
            return None
        total = 0
        for criterion in rubric.criteria:
            options = criterion.get("options", [])
            if options:
                total += max((opt.get("marks", 0) for opt in options), default=0)
        return total if total > 0 else None

    def student_view(self, context=None):
        """
        The primary view of the XBlock, shown to students
        when viewing courses.
        """
        user = self.runtime.get_real_user()
        is_course_staff = has_access(user, "staff", self.course_id)
        TAS_MICROFRONTEND_URL = getattr(settings, "TAS_MICROFRONTEND_URL", "http://apps.local.openedx.io:2022")
        assigment_submission_url = f"{TAS_MICROFRONTEND_URL}/submission/{self.location}"
        assigment_review_url = f"{TAS_MICROFRONTEND_URL}/instructor/grade-submissions/{self.location}"
        assigment_status, assigment_pdf_url, assigment_feedback = self.get_assigment_status()
        assigment_due_passed = self.is_past_due()

        # Fallback grade publish: the grade is normally pushed immediately when
        # the instructor approves a submission (via the push_grade_to_lms Celery
        # task).  Re-publishing here ensures the LMS gradebook stays in sync even
        # if the async task was missed or not yet processed when the student loads
        # the page.
        assigment_earned_score = None
        assigment_max_score = None
        if not is_course_staff and assigment_status == "approved" and assigment_feedback:
            max_possible = self.max_score() or 0
            if max_possible > 0:
                earned = sum(r.get("marks", 0) for r in (assigment_feedback.get("rubrics") or []))
                self.runtime.publish(
                    self,
                    "grade",
                    {
                        "value": earned,
                        "max_value": max_possible,
                    },
                )
                assigment_earned_score = earned
                assigment_max_score = max_possible

        context = {
            "display_name": self.display_name,
            "template_type": self.template_type,
            "template": self.template,
            "instructions": self.instructions,
            "is_course_staff": is_course_staff,
            "assigment_submission_url": assigment_submission_url,
            "assigment_review_url": assigment_review_url,
            "assigment_status": assigment_status,
            "assigment_due_passed": assigment_due_passed,
            "assigment_pdf_url": assigment_pdf_url,
            "assigment_feedback": assigment_feedback,
            "assigment_earned_score": assigment_earned_score,
            "assigment_max_score": assigment_max_score,
        }
        html = self.render_template("tas.html", context)

        frag = Fragment(html)
        frag.add_css(self.load_resource("static/css/tas.css"))
        frag.add_javascript(self.load_resource("static/js/tas.js"))
        frag.initialize_js("TASXBlockInitView")
        return frag

    def studio_view(self, context=None):
        """
        The secondary view of the XBlock, shown to teachers
        when editing the XBlock.
        """
        assignment_template_types = TemplateType.objects.all()
        assignment_templates = Template.objects.all()
        available_rubrics = Rubric.objects.filter(is_active=True).order_by("name")
        context = {
            "display_name": self.display_name,
            "current_template_type": self.template_type,
            "current_template": self.template,
            "assignment_template_types": assignment_template_types,
            "assignment_templates": assignment_templates,
            "instructions": self.instructions,
            "current_rubric_id": self.rubric_id,
            "available_rubrics": available_rubrics,
        }
        html = self.render_template("tas_edit.html", context)

        frag = Fragment(html)
        frag.add_css(self.load_resource("static/css/tas_edit.css"))
        frag.add_javascript(self.load_resource("static/js/tas_edit.js"))
        frag.initialize_js("TASXBlockInitEdit")
        return frag

    @XBlock.json_handler
    def save_studio(self, data, suffix=""):
        """
        Handles studio (edit mode) AJAX requests to save the XBlock configuration.

        Persists the main editable fields to the XBlock instance and corresponding TemplateBlock record.

        Args:
            data (dict): Dictionary containing updated XBlock settings from the Studio frontend.
            suffix (str): Optional suffix (unused).

        Returns:
            dict: Result dictionary indicating success/failure.
        """
        # Extract and update XBlock fields from incoming data.
        self.display_name = data.get("display_name", self.display_name)
        self.template_type = data.get("template_type", self.template_type)
        self.template = data.get("template", self.template)
        self.instructions = data.get("instructions", self.instructions)
        self.rubric_id = data.get("rubric_id", self.rubric_id)

        try:
            # Fetch associated Template object (raise clear error if not found).
            template_obj = Template.objects.get(id=self.template)
        except Template.DoesNotExist:
            return {"result": "error", "message": "Template not found."}

        try:
            # Identify the current user performing the save.
            user_id = self.runtime.user_id
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return {"result": "error", "message": "User not found."}

        # Resolve the Rubric record from the selected rubric_id.
        rubric_obj = None
        if self.rubric_id:
            try:
                rubric_obj = Rubric.objects.get(pk=self.rubric_id, is_active=True)
            except (Rubric.DoesNotExist, ValueError):
                return {"result": "error", "message": "Selected rubric not found."}

        # Persist changes to TemplateBlock, creating or updating as needed.
        TemplateBlock.objects.update_or_create(
            usage_key=str(self.location),  # XBlock instance usage key
            course_key=str(self.course_id),
            defaults={
                "template": template_obj,
                "display_name": self.display_name,
                "instructions": self.instructions,
                "rubric": rubric_obj,
                "assigned_by": user,
                "sort_order": 0,
            },
        )

        return {"result": "success"}

    # TO-DO: change this to create the scenarios you'd like to see in the
    # workbench while developing your XBlock.
    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            (
                "TASXBlock",
                """<tas/>
             """,
            ),
            (
                "Multiple TASXBlock",
                """<vertical_demo>
                <tas/>
                <tas/>
                <tas/>
                </vertical_demo>
             """,
            ),
        ]
