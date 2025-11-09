from odoo import models, api
import logging
import json

_logger = logging.getLogger(__name__)


class ApiManagerRequest(models.Model):
    _inherit = 'api_manager.request'

    def send_request(self):
        res = super(ApiManagerRequest, self).send_request()

        external_id = self.get_external_id()
        record_xml_id = external_id.get(self.id, '')

        if record_xml_id == 'api_manager.api_request_dotykacka_refresh_token':
            self._save_dotykacka_token()
        if record_xml_id == 'api_manager.api_request_dotykacka_get_products':
            self._sync_products_from_response()

        return res

    def _save_dotykacka_token(self):
        try:
            if hasattr(self, 'response') and self.response:
                try:
                    response_data = self.response.json()

                    token = response_data.get('accessToken') or response_data.get('token')

                    if token:
                        self.env['ir.config_parameter'].sudo().set_param(
                            'dotykacka.api_token',
                            token
                        )
                        providers = self.env['api_manager.provider'].sudo().search([])
                        if providers:
                            providers.write({'token': token})
                    else:
                        _logger.warning("Token not found in response")
                except Exception as json_error:
                    _logger.error(f"Error parsing response JSON: {json_error}")
            else:
                _logger.warning("No response object available")

        except Exception as e:
            _logger.error(f"Error saving Dotykacka token: {e}")
            import traceback
            traceback.print_exc()

    @api.model
    def cron_refresh_dotykacka_token(self):
        try:
            request = self.env.ref('api_manager.api_request_dotykacka_refresh_token')

            if request:
                _logger.info("Starting automatic Dotykacka token refresh via cron")
                request.send_request()
                _logger.info("Dotykacka token refresh completed successfully")
            else:
                _logger.error("Dotykacka refresh token request not found")

        except Exception as e:
            _logger.error(f"Error in cron_refresh_dotykacka_token: {e}")
            import traceback
            traceback.print_exc()


    def _sync_products_from_response(self):
        results = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0
        }
        response_data = self.response.json()

        if not response_data:
            _logger.warning("No response data to sync products")
            return

        products_data = response_data.get('data', [])

        if not products_data:
            _logger.warning("No products found in API response")
            return

        ProductTemplate = self.env['product.template'].sudo()

        for product_data in products_data:
            try:
                normalized_data = self._normalize_product_data(product_data)

                product = ProductTemplate.sync_from_dotykachka(normalized_data)

                if product:
                    if product.create_date == product.write_date:
                        results['created'] += 1
                    else:
                        results['updated'] += 1
                else:
                    results['skipped'] += 1

            except Exception as e:
                _logger.error(f"Error syncing product {product_data.get('id')}: {str(e)}", exc_info=True)
                results['errors'] += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Products Synced',
                'message': f"Created: {results['created']}, Updated: {results['updated']}, Errors: {results['errors']}",
                'type': 'success' if results['errors'] == 0 else 'warning',
                'sticky': False,
            }
        }

    def _normalize_product_data(self, api_data):
        """Преобразует формат API Dotykachka в формат webhook"""
        return {
            'productid': api_data.get('id'),
            'name': api_data.get('name'),
            'pricewithvat': float(api_data.get('priceWithVat', 0)),
            'pricewithoutvat': float(api_data.get('priceWithoutVat', 0)),
            'vat': float(api_data.get('vat', 0)),
            'categoryid': api_data.get('_categoryId'),
            'ean': api_data.get('ean'),
            'plu': api_data.get('plu'),
            'barcode': api_data.get('ean'),
            'defaultcode': api_data.get('plu'),
            'description': api_data.get('description'),
            'alternativename': api_data.get('alternativeName'),
            'subtitle': api_data.get('subtitle'),
            'units': api_data.get('unit'),
            'display': 1 if api_data.get('display') else 0,
            'deleted': 1 if api_data.get('deleted') else 0,
            'stockdeduct': 1 if api_data.get('stockDeduct') else 0,
        }