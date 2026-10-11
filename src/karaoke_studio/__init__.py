"""Karaoke Studio core package.

Keep this module dependency-free: the isolated Yohane interpreter imports the
stdlib-only worker through this package but deliberately does not install the
web application's Pydantic stack.
"""

CORE_VERSION = "0.1.0"
SCHEMA_VERSION = 1

__all__ = ["CORE_VERSION", "SCHEMA_VERSION"]
