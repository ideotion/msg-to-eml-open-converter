"""Custom exceptions raised by msg2eml."""

from __future__ import annotations


class Msg2EmlError(Exception):
    """Base class for all errors raised deliberately by msg2eml."""


class ConversionError(Msg2EmlError):
    """Raised when a .msg file cannot be converted to .eml."""


class UnreadableMsgFileError(ConversionError):
    """Raised when a .msg file cannot be opened or parsed at all."""
