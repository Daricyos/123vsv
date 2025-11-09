"""Module for managing API Providers."""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class APIProvider(models.Model):
    """API Providers manager."""

    _name = 'api_manager.provider'
    _description = "Provider"

    name = fields.Char(store=True)
    internal_reference = fields.Char(store=True)
    server_domain = fields.Char(store=True, required=True)
    server_scheme = fields.Selection(
        selection=[
            ('http', "HTTP"),
            ('https', "HTTPS"),
            ('ftp', "FTP"),
            ('sftp', "SFTP"),
            ('smtp', "SMTP"),
            ('pop', "POP"),
        ],
        default='https',
        required=True,
        string="URL Scheme",
    )
    server_url = fields.Char("Server URL", compute="_compute_server_url")
    authentication_method = fields.Selection(
        selection=[
            ('none', "No auth"),
            ('basic', "Basic"),
            ('digest', "Digest"),
            ('api_token', "API Token"),
            ('bearer_token', "Bearer Token"),
            # ('oauth1', "OAuth 1.0"),
            # ('oauth2', "OAuth 2.0"),
        ],
        string="Auth Method",
        default='none',
        required=True,
    )
    username = fields.Char(store=True, default=None)
    password = fields.Char(store=True, default=None)
    digest_alg = fields.Selection(
        selection=[('md5', "MD5"), ('sha256', "SHA-256")], string="Hash Algorithm", default='md5'
    )
    key = fields.Char("Token Key", store=True, default=None)
    value = fields.Char("Token Value", store=True, default=None)
    token_method = fields.Selection(
        selection=[('header', "Header"), ('query_arg', "Query Params")],
        string="Method",
        default='header',
    )
    token = fields.Char(store=True, default=None)
    dynamic_token = fields.Boolean("Is Dynamic Token")
    rel_companies = fields.Many2many('res.company', string="Related Companies")

    @api.depends('server_domain', 'server_scheme')
    def _compute_server_url(self):
        """Compute full url."""
        for record in self:
            record.server_url = f"{record.server_scheme}://{record.server_domain}"

    @api.constrains('server_domain')
    def _check_server_domain(self):
        """Validate server domain."""
        for provider in self:
            if provider.server_domain[-1] == "/":
                raise ValidationError(_("Server Domain cannot end with '/' character!"))
