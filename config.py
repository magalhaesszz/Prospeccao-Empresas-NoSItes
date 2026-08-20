"""Compatibility module. New code uses prospector.settings.Settings directly."""
from prospector.settings import settings

CONFIG = settings.legacy_config()
