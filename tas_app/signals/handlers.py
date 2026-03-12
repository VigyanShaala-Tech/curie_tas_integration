"""
Manage signal handlers here
"""

import logging

from django.dispatch import receiver
from xmodule.modulestore.django import SignalHandler


log = logging.getLogger(__name__)
