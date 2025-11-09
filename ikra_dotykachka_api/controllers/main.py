from odoo import http
from odoo.http import request
import json
import logging
import requests


_logger = logging.getLogger(__name__)


class DotyWebhook(http.Controller):
    @http.route(['/doty/product/webhook', '/doty/product/webhook/<string:cloud_id>'],
                type='http', auth='public', csrf=False, methods=['POST'])
    def webhook_receive(self, cloud_id=None, **post):
        try:
            try:
                data = json.loads(request.httprequest.data)
            except json.JSONDecodeError:
                data = post

            if not data:
                _logger.warning("Empty webhook data received")
                return self._response({'status': 'error', 'message': 'No data'}, 400)

            # Если cloud_id не передан в URL, пытаемся получить из старых настроек
            if not cloud_id:
                cloud_id = request.env['ir.config_parameter'].sudo().get_param('dotykacka.cloud_id')
                _logger.warning("No cloud_id in URL, using legacy config")

            if not isinstance(data, list):
                data = [data]

            results = {
                'created': 0,
                'updated': 0,
                'archived': 0,
                'errors': 0
            }

            ProductTemplate = request.env['product.template'].sudo()

            for product_data in data:
                try:
                    product = ProductTemplate.sync_from_dotykachka(product_data, cloud_id=cloud_id)

                    if not product:
                        results['errors'] += 1
                        continue

                    if product_data.get('deleted') == 1:
                        results['archived'] += 1
                    elif product.create_date == product.write_date:
                        results['created'] += 1
                    else:
                        results['updated'] += 1

                except Exception as e:
                    _logger.error(f"Error processing product: {str(e)}", exc_info=True)
                    results['errors'] += 1

            return self._response({
                'status': 'ok',
                'results': results
            })

        except Exception as e:
            _logger.error(f"Webhook error: {str(e)}", exc_info=True)
            return self._response({
                'status': 'error',
                'message': str(e)
            }, 500)

    @http.route(['/doty/order/webhook', '/doty/order/webhook/<string:cloud_id>'],
                type='http', auth='public', csrf=False, methods=['POST'])
    def webhook_order(self, cloud_id=None, **post):
        try:
            try:
                data = json.loads(request.httprequest.data)
            except json.JSONDecodeError:
                data = post

            # Если cloud_id не передан в URL, пытаемся получить из старых настроек
            if not cloud_id:
                cloud_id = request.env['ir.config_parameter'].sudo().get_param('dotykacka.cloud_id')
                _logger.warning("No cloud_id in URL, using legacy config")

            if not isinstance(data, list):
                data = [data]

            results = {
                'created': 0,
                'updated': 0,
                'skipped': 0,
                'errors': 0,
                'error_details': []
            }

            SaleOrder = request.env['sale.order'].sudo()

            for order_data in data:
                try:
                    order_id = order_data.get('orderid')
                    branch_id = order_data.get('branchid')

                    if not order_id or not branch_id:
                        results['errors'] += 1
                        results['error_details'].append({
                            'order': order_data.get('orderseriesid', 'unknown'),
                            'error': 'Missing required fields'
                        })
                        continue

                    order = SaleOrder.sync_from_dotykachka(order_data, cloud_id=cloud_id)

                    if not order:
                        results['errors'] += 1
                        results['error_details'].append({
                            'order': order_data.get('orderseriesid', order_id),
                            'error': 'Failed to create/update order'
                        })
                        continue

                    if hasattr(order, '_sync_result'):
                        if order._sync_result == 'created':
                            results['created'] += 1
                        elif order._sync_result == 'updated':
                            results['updated'] += 1
                        elif order._sync_result == 'skipped':
                            results['skipped'] += 1
                    else:
                        results['updated'] += 1

                except Exception as e:
                    _logger.error(f"Error processing order {order_data.get('orderid')}: {str(e)}", exc_info=True)
                    results['errors'] += 1
                    results['error_details'].append({
                        'order': order_data.get('orderseriesid', order_data.get('orderid')),
                        'error': str(e)
                    })

            response_data = {
                'status': 'ok',
                'results': results
            }

            if results['errors'] > 0 and results['error_details']:
                response_data['errors'] = results['error_details']

            return self._response(response_data)

        except Exception as e:
            _logger.error(f"Order webhook error: {str(e)}", exc_info=True)
            return self._response({
                'status': 'error',
                'message': str(e)
            }, 500)



    def _response(self, data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[
                ('Content-Type', 'application/json'),
                ('Cache-Control', 'no-cache')
            ],
            status=status
        )
