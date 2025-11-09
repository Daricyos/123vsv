from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dotykachka_customer_id = fields.Char(string="Dotykachka customer ID", index=True)

    _sql_constraints = [
        ('dotykachka_customer_id_unique', 'UNIQUE(dotykachka_customer_id)',
         'Dotykačka Customer ID must be unique!')
    ]