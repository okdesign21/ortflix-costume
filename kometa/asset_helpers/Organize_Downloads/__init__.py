# ruff: noqa: N999
"""Kometa Assets Organizer - Automated asset organization for Kometa collections."""

try:
    from importlib.metadata import version

    __version__ = version("kometa-assets-organizer")
except Exception:
    __version__ = "0.0.0+unknown"

__author__ = "okdesign21"
__license__ = "MIT"

from .handlers import Organizer

__all__ = ["Organizer"]
