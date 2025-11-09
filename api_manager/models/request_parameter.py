"""Module for Request Arguments."""

from collections import defaultdict
from itertools import product
from typing import Dict, Generator

from odoo import fields, models


class APIRequestParameter(models.Model):
    """API Request manager of URL parameters."""

    _name = "api_manager.request_parameter"
    _description = "Request Parameter"

    provider = fields.Many2one('api_manager.provider')
    key = fields.Char(required=True, tracking=True)
    value = fields.Char(required=True, tracking=True)
    company_id = fields.Many2one('res.company')

    _sql_constraints = [
        ('key_val_uniq', 'unique (provider, key, company_id)', "This combination exists already!"),
    ]

    def get_groups_by_key(self) -> Dict[str, set]:
        """Return grouped recordset by keys without duplicate values."""
        grouped = defaultdict(set)
        for param in self:
            grouped[param.key].add(param.value)
        deduplicated = {key: set(value_list) for key, value_list in grouped.items()}
        return deduplicated

    def get_combinations(self) -> Generator[Dict[str, str], None, None]:
        """Return list of all possible combinations for the recordset."""
        grouped = self.get_groups_by_key()
        for values in product(*grouped.values()):
            yield dict(zip(grouped.keys(), values))

    def name_get(self):
        """Overloading the method to make a name, since it doesn't have own."""
        result = []
        for rec in self:
            result.append((rec.id, f"{rec.company_id.name} / {rec.provider.name} / {rec.key}"))
        return result
