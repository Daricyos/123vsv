from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    dotykacka_api_token = fields.Char(string="Dotykacka API Token",
                                  config_parameter='dotykacka.api_token')

    dotykacka_cloud_id = fields.Char(string="Dotykacka Cloud ID", config_parameter='dotykacka.cloud_id')