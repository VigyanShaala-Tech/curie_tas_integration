"""TO-DO: Write a description of what this XBlock is."""

import os
import json
import pkg_resources
from django.template import Context
from django.conf import settings
from xblock.core import XBlock
from xblock.fields import Float, Scope, String, List
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader

from django.contrib.auth.models import User
from lms.djangoapps.courseware.access import has_access
from tas_app.models import TemplateBlock, Template, TemplateType, Submission


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

    rubrics = List(
        display_name=_("Rubrics"),
        scope=Scope.settings,
        default=[
            {
                "criterion": "Ideas",
                "options": [
                    {
                        "name": "Poor",
                        "marks": 1,
                        "description": "Difficult for the reader to discern the main idea.  Too brief or too repetitive to establish or maintain a focus.",
                    },
                    {
                        "name": "Fair",
                        "marks": 3,
                        "description": "Presents a unifying theme or main idea, but may include minor tangents.  Stays somewhat focused on topic and task.",
                    },
                    {
                        "name": "Good",
                        "marks": 5,
                        "description": "Presents a unifying theme or main idea without going off on tangents.  Stays completely focused on topic and task.",
                    },
                ],
            },
            {
                "criterion": "Content",
                "options": [
                    {
                        "name": "Poor",
                        "marks": 1,
                        "description": "Includes little information with few or no details or unrelated details.  Unsuccessful in attempts to explore any facets of the topic.",
                    },
                    {
                        "name": "Fair",
                        "marks": 2,
                        "description": "Includes little information and few or no details.  Explores only one or two facets of the topic.",
                    },
                    {
                        "name": "Good",
                        "marks": 3,
                        "description": "Includes sufficient information and supporting details. (Details may not be fully developed; ideas may be listed.)  Explores some facets of the topic.",
                    },
                    {
                        "name": "Excellent",
                        "marks": 5,
                        "description": "Includes in-depth information and exceptional supporting details that are fully developed.  Explores all facets of the topic.",
                    },
                ],
            },
        ],
        help=_("List of rubrics for evaluation"),
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
                    "rubrics": fb.rubrics or [],
                }
            except Exception:
                pass
        except Exception:
            return "not_submitted", None, None
        return submission.status, assigment_pdf_url, feedback

    def max_score(self):
        """
        Return the maximum achievable score across all rubric criteria.

        For each criterion the maximum is the highest marks value among its
        options.  The overall maximum is the sum of per-criterion maximums.
        Returns None when no rubrics are configured so the runtime treats this
        block as ungraded until rubrics are set.
        """
        total = 0
        for criterion in self.rubrics:
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

        # Publish grade to the LMS gradebook when a student's submission has been
        # approved by an instructor.  This uses the "lazy publish" pattern: the
        # grade is (re-)published each time the student loads the page so it
        # always reflects the latest approved feedback without requiring the
        # instructor-facing REST API to have direct access to the XBlock runtime.
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
        context = {
            "display_name": self.display_name,
            "current_template_type": self.template_type,
            "current_template": self.template,
            "assignment_template_types": assignment_template_types,
            "assignment_templates": assignment_templates,
            "instructions": self.instructions,
            "rubrics": json.dumps(self.rubrics),
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
        self.rubrics = data.get("rubrics", [])

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

        # Persist changes to TemplateBlock, creating or updating as needed.
        TemplateBlock.objects.update_or_create(
            usage_key=str(self.location),  # XBlock instance usage key
            course_key=str(self.course_id),
            defaults={
                "template": template_obj,
                "display_name": self.display_name,
                "instructions": self.instructions,
                "rubrics": self.rubrics,
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
