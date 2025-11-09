from odoo import api, fields, models

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    dotykachka_employee_id = fields.Integer('Dotykachka employee ID')
