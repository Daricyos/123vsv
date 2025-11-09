"""Module for managing API Providers."""

import logging
import time

from odoo import api, fields, models
from dateutil.relativedelta import relativedelta

from ..utils import exceptions

LOG_ORIGIN = __name__
_logger = logging.getLogger(LOG_ORIGIN)


class APILogger(models.Model):
    """API Logs of incomming and outgoing traffic."""

    _name = 'api_manager.logger'
    _description = "API Log"

    created_at = fields.Datetime(index=True, default=fields.Datetime.now, required=True)
    origin = fields.Char(required=True)
    direction = fields.Selection(
        [
            ('incoming', 'Incoming'),
            ('outgoing', 'Outgoing'),
        ],
        string="Log Type",
        default='response',
        required=True,
    )
    data = fields.Char(required=True)

    def _preprocess(self, method, *args, **kwargs):
        """
        Call object method in isolated transaction.

        Creates new environment and database cursor.
        Object method is executed regardless if caller has already closed its own transaction.
        Cursor is closed after the transaction and all references thrown away,
        so there is no access to closed cursor

        :param method: Method that will be called
        :param args: Passed non-keyword arguments
        :param kwargs: Passed keyword argumentsapi_log

        :return: Return data from called method
        """
        arguments = locals()  # Get arguments before defining any local variable
        arguments = {k: v for k, v in arguments.items() if k in ['args', 'kwargs']}
        args = arguments['args']
        res = None
        _logger.debug("Creating isolated transaction for logging.")
        self.env.flush_all()
        with self.pool.cursor() as new_cr:
            new_env = api.Environment(new_cr, self.env.uid, self.env.context)
            new_self = self.with_env(new_env)
            callable_method = self._get_method(new_self.env, method)
            res = callable_method(*args, **kwargs)
            new_self._commit_changes()  # pylint: disable=W0212
        _logger.debug("Closing isolated transaction for logging.")  # Log used method
        self.env.flush_all()
        return res

    def _commit_changes(self, attempt=1):
        """Commit Changes to database."""
        try:
            _logger.info("Committing API Log")  # Log used method
            self.env.cr.commit()  # pylint:disable=E8102
        except Exception as error:  # pylint:disable=W0703
            _logger.error("Committing attempt %s of API Log failed with error: %s", attempt, error)
            if attempt < 5:
                time.sleep((2 ** (attempt - 1)))  # Every next attempt will wait twice as long
                self._commit_changes(attempt + 1)
                return
            self.env.cr.rollback()
        else:
            _logger.info("Committing API Log was success!")  # Log used method

    def write(self, vals):  # pylint:disable=W8106
        """Override to use new environment."""
        return self._preprocess('write', vals)

    def create(self, values):  # pylint:disable=W8106
        """Override to use new environment."""
        return self._preprocess('create', values)

    def _get_method(self, env, method_name):
        """
        Return callable method of specified object.

        :param odoo.api.Environment env: Odoo environment
        :param method_name: Method name

        :raises errors.InvalidMethod: if method doesn't exist or is not callable
        :return: Callable method
        """
        parent = super(APILogger, self)
        if hasattr(parent, method_name):
            method = getattr(parent, method_name)
            if callable(method):
                return method
        raise exceptions.InvalidMethod(
            parent.__class__.__name__, method_name, env=env, origin=LOG_ORIGIN, severity='error'
        )

    def _clear_logs(self):
        """Clear logs older then one month."""
        for log in self.search(
            [('created_at', '<', fields.Datetime.now() - relativedelta(months=1))]
        ):
            log.unlink()
