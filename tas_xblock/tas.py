"""TO-DO: Write a description of what this XBlock is."""

import os
import json
import pkg_resources
from django.template import Context

from xblock.core import XBlock
from xblock.fields import Scope, String, List
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader

from django.contrib.auth.models import User
from lms.djangoapps.courseware.access import has_access
from tas_app.models import TemplateBlock, Template, TemplateType


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

    icon_class = "other"

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
        default=[],
        help=_("List of rubrics for evaluation"),
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

    def student_view(self, context=None):
        """
        The primary view of the XBlock, shown to students
        when viewing courses.
        """
        user = self.runtime.get_real_user()
        is_course_staff = has_access(user, "staff", self.course_id)

        context = {
            "display_name": self.display_name,
            "template_type": self.template_type,
            "template": self.template,
            "instructions": self.instructions,
            "is_course_staff": is_course_staff,
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
