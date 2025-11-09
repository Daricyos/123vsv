from odoo import api, fields, models, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dotykachka_id = fields.Char(
        string='Dotykachka ID',
        readonly=True,
        index = True,
        copy = False
    )
    dotykachka_category_id = fields.Char(string='Dotykachka Category ID')
    dotykachka_ean = fields.Char(string='EAN')
    dotykachka_plu = fields.Char(string='PLU')
    dotykachka_vat = fields.Float(string='VAT Rate')
    dotykachka_alternative_name = fields.Char(string='Alternative Name')
    dotykachka_subtitle = fields.Char(string='Subtitle')
    dotykachka_units = fields.Char(string='Units')
    dotykachka_last_sync = fields.Datetime(string='Last Sync', readonly=True)

    _sql_constraints = [
        ('dotykachka_id_unique', 'UNIQUE(dotykachka_id)',
         'Dotykachka ID must be unique!')
    ]

    @api.model
    def sync_from_dotykachka(self, product_data):
        try:
            dotykachka_id = str(product_data.get('productid'))
            if not dotykachka_id:
                _logger.error("Missing productid in webhook data")
                return False

            PT = self.env['product.template'].with_user(SUPERUSER_ID)

            product = PT.search([('dotykachka_id', '=', dotykachka_id)], limit=1)
            vals = self._prepare_product_vals(product_data)

            if product_data.get('deleted') == 1:
                if product:
                    product.sudo().write({'active': False})
                    _logger.info(f"Product {dotykachka_id} archived")
                return product

            if product:
                product.sudo().write(vals)
                _logger.info(f"Product {dotykachka_id} updated")
            else:
                vals['dotykachka_id'] = dotykachka_id
                product = PT.sudo().create(vals)
                _logger.info(f"Product {dotykachka_id} created")

            return product

        except Exception as e:
            _logger.error(f"Error syncing product: {str(e)}", exc_info=True)
            return False

    @api.model
    def _prepare_product_vals(self, data):
        vals = {
            'name': data.get('name', 'Unknown Product'),
            'list_price': float(data.get('pricewithvat', 0)),
            'standard_price': float(data.get('pricewithoutvat', 0)),
            'active': data.get('deleted', 0) != 1,
            'sale_ok': data.get('display', 1) == 1,
            'purchase_ok': True,
            'type': 'consu' if data.get('stockdeduct', 0) == 1 else 'service',
            'dotykachka_last_sync': fields.Datetime.now(),
        }

        if data.get('description'):
            vals['description'] = data['description']
        if data.get('barcode') or data.get('ean'):
            vals['barcode'] = data.get('ean') or data.get('barcode')

        if data.get('defaultcode') or data.get('plu'):
            vals['default_code'] = data.get('plu') or data.get('defaultcode')

        vals.update({
            'dotykachka_category_id': str(data.get('categoryid', '')),
            'dotykachka_ean': data.get('ean', ''),
            'dotykachka_plu': data.get('plu', ''),
            'dotykachka_vat': float(data.get('vat', 0)),
            'dotykachka_alternative_name': data.get('alternativename', ''),
            'dotykachka_subtitle': data.get('subtitle', ''),
            'dotykachka_units': data.get('units', ''),
        })

        return vals