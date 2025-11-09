"""Custom Exceptions."""

import logging

from odoo import api
from odoo.exceptions import UserError


class LoggedError(UserError):
    """Logged Exception."""

    def __init__(self, message, **kwargs):
        """
        Initialize error and set error message.

        :param message:
        :param value:
        :param kwargs:
        """
        super(LoggedError, self).__init__(message)
        if kwargs:
            self.log_message(message=message, **kwargs)

    @staticmethod
    def log_message(
        env: api.Environment = None, origin: str = "", message: str = "", severity: str = 'warning'
    ) -> None:
        """
        Log message from origin.

        :param env: odoo.api.Environment class
        :param origin: String representing origin of Exception
        :param message: Message
        :param severity: Logging severity
        """
        logger = logging.getLogger(origin)
        method = getattr(logger, severity)
        method(message)


class InvalidMethod(LoggedError):
    """Exception raised when object doesn't contain specific callable method."""

    def __init__(self, obj_name: str, method_name: str, **kwargs):
        """Initialize error and set error message."""
        message = f"Object {obj_name} doesn't contain callable method '{method_name}'!"
        super(InvalidMethod, self).__init__(message, **kwargs)


class InvalidResponse(LoggedError):
    """Exception raised for empty record data."""

    def __init__(self, obj_name, response, **kwargs):
        """Initialize error and set error message."""
        message = f"Request {obj_name} didn't return valid response: {response}!"
        super(InvalidResponse, self).__init__(message, **kwargs)