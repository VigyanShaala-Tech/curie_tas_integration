"""TO-DO: Write a description of what this XBlock is."""

import os
import pkg_resources
from django.template import Context

from xblock.core import XBlock
from xblock.fields import Scope, String
from xblock.fragment import Fragment
from xblockutils.resources import ResourceLoader
from tas_app.models import Template, TemplateType
from xblock.fields import Scope, String, List
import json
from tas_app.models import TemplateBlock, Template
from django.contrib.auth.models import User
from lms.djangoapps.courseware.access import has_access

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

        self.display_name = data["display_name"]
        self.template_type = data["template_type"]
        self.template = data["template"]
        self.instructions = data["instructions"]
        self.rubrics = data.get("rubrics", [])

        try:
            template_obj = Template.objects.get(id=self.template)

            user_id = self.runtime.user_id
            user = User.objects.get(id=user_id)

            TemplateBlock.objects.update_or_create(
                usage_key=str(self.location),
                course_key=str(self.course_id),
                defaults={
                    "template": template_obj,
                    "display_name": self.display_name,
                    "template_type": self.template_type,
                    "instructions": self.instructions,
                    "rubrics": self.rubrics,
                    "assigned_by": user,
                    "sort_order": 0,
                }
            )

        except Exception as e:
            print("TemplateBlock Save Error:", e)

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
