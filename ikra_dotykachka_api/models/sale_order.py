from odoo import api, fields, models, SUPERUSER_ID
from odoo.exceptions import UserError
import logging
import requests

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    point_of_sale_dotykacka = fields.Char(
        string='Point of sale ID',
        readonly=True
    )
    order_id_dotykacka = fields.Char(
        string='Unique order ID in Dotykačka',
        readonly=True
    )
    dotykacka_cloud_id = fields.Char(
        string='Dotykacka Cloud ID',
        readonly=True,
        index=True,
        help='ID облака, из которого синхронизирован этот заказ'
    )
    check_number_dotykacka = fields.Char(
        string='Check number',
        readonly=True
    )
    dotykacka_last_sync = fields.Datetime(
        string='Last Sync',
        readonly=True
    )

    _sql_constraints = [
        ('order_id_dotykacka_cloud_unique', 'UNIQUE(order_id_dotykacka, dotykacka_cloud_id)',
         'Dotykačka Order ID must be unique per cloud!')
    ]

    @api.model
    def sync_from_dotykachka(self, order_data, cloud_id=None):
        try:
            order_id = str(order_data.get('orderid'))
            branch_id = str(order_data.get('branchid'))

            if not cloud_id:
                _logger.warning("No cloud_id provided, using legacy mode")
                cloud_id = self.env['ir.config_parameter'].sudo().get_param('dotykacka.cloud_id')

            SO = self.env['sale.order'].with_user(SUPERUSER_ID)

            # Ищем заказ по order_id_dotykacka И cloud_id
            domain = [('order_id_dotykacka', '=', order_id)]
            if cloud_id:
                domain.append(('dotykacka_cloud_id', '=', cloud_id))

            existing_order = SO.search(domain, limit=1)

            if existing_order and existing_order.state in ['done', 'cancel']:
                _logger.info(f"Order {order_id} from cloud {cloud_id} already processed ({existing_order.state})")
                return existing_order

            order_items = self._fetch_order_items(order_id, branch_id, cloud_id)

            if not order_items:
                _logger.warning(f"No items found for order {order_id} from cloud {cloud_id}")

                # Подготовка значений заказа
            vals = self._prepare_order_vals(order_data, order_items or [], cloud_id)

            if existing_order:
                existing_order.sudo().write(vals)
                order = existing_order
            else:
                vals['order_id_dotykacka'] = order_id
                vals['dotykacka_cloud_id'] = cloud_id
                order = SO.sudo().create(vals)

            self._process_invoice_and_payment(order, order_data)

            return order

        except Exception as e:
            _logger.error(f"Error syncing order {order_data.get('orderid', 'unknown')}: {str(e)}", exc_info=True)
            return False

    @api.model
    def _process_invoice_and_payment(self, order, order_data):
        try:
            if order.state != 'sale':
                return
            if order.invoice_ids:
                return

            is_paid = order_data.get('completed', False)
            total_paid = float(order_data.get('totalPaid', 0))
            invoice = order._create_invoices()

            if not invoice:
                _logger.warning(f"Failed to create invoice for order {order.order_id_dotykacka}")
                return

            invoice.action_post()

            if is_paid and total_paid > 0:
                self._register_payment(invoice, order_data)

        except Exception as e:
            _logger.error(f"Error processing invoice for order {order.order_id_dotykacka}: {str(e)}", exc_info=True)

    @api.model
    def _register_payment(self, invoice, order_data):
        """
        Регистрирует оплату для инвойса
        """
        try:
            total_paid = float(order_data.get('totalPaid', 0))

            if total_paid <= 0:
                _logger.warning(f"Total paid is 0 for invoice {invoice.name}")
                return

            # Ищем метод оплаты (можно настроить под свои нужды)
            payment_method = self.env['account.payment.method'].sudo().search([
                ('code', '=', 'manual'),
                ('payment_type', '=', 'inbound')
            ], limit=1)

            if not payment_method:
                _logger.error("Payment method 'manual' not found")
                return

            # Ищем журнал для оплаты (банк или касса)
            journal = self.env['account.journal'].sudo().search([
                ('type', 'in', ['bank', 'cash']),
                ('company_id', '=', invoice.company_id.id)
            ], limit=1)

            if not journal:
                _logger.error("No bank/cash journal found")
                return

            # Определяем дату оплаты
            payment_date = fields.Date.today()
            if order_data.get('completed_date'):
                try:
                    # Предполагаем формат ISO: 2025-11-03T14:30:00
                    completed_date = fields.Datetime.from_string(order_data['completed_date'])
                    payment_date = completed_date.date()
                except:
                    pass

            # Создаём платёж
            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': invoice.partner_id.id,
                'amount': total_paid,
                'date': payment_date,
                'payment_method_id': payment_method.id,
                'journal_id': journal.id,
                'ref': f"Dotykačka Order {order_data.get('orderseriesid', '')}",
            }

            payment = self.env['account.payment'].sudo().create(payment_vals)
            payment.action_post()

            _logger.info(f"Payment {payment.name} created for invoice {invoice.name}")

            # Связываем платёж с инвойсом
            # В Odoo 18 используется reconcile
            invoice_line = invoice.line_ids.filtered(
                lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable')
            )
            payment_line = payment.line_ids.filtered(
                lambda line: line.account_id.account_type in ('asset_receivable', 'liability_payable')
            )

            if invoice_line and payment_line:
                (invoice_line + payment_line).reconcile()
                _logger.info(f"Payment reconciled with invoice {invoice.name}")

        except Exception as e:
            _logger.error(f"Error registering payment: {str(e)}", exc_info=True)

    @api.model
    def _fetch_order_items(self, order_id, branch_id, cloud_id=None):
        try:
            ICP = self.env['ir.config_parameter'].sudo()

            if not cloud_id:
                cloud_id = ICP.get_param('dotykacka.cloud_id', '388478152')

            # Получаем токен для конкретного облака
            cloud_config = self.env['dotykacka.cloud.config'].sudo().search([
                ('cloud_id', '=', cloud_id),
                ('active', '=', True)
            ], limit=1)

            if cloud_config and cloud_config.api_token:
                api_token = cloud_config.api_token
            else:
                # Fallback на старые настройки
                api_token = ICP.get_param('dotykacka.api_token')

            if not api_token:
                raise UserError("Dotykačka API token not configured")

            url = f"https://api.dotykacka.cz/v2/clouds/{cloud_id}/order-items?sort=-created&page=1"

            headers = {
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json'
            }

            response = requests.get(url, headers=headers, timeout=30)
            print(response.json())

            if response.status_code != 200:
                _logger.error(f"API error {response.status_code}: {response.text}")
                return []

            response_data = response.json()
            all_items = response_data.get('data', [])

            order_items = [
                item for item in all_items
                if str(item.get('_orderId')) == str(order_id)
            ]

            return order_items

        except Exception as e:
            _logger.error(f"Error fetching order items: {str(e)}", exc_info=True)
            return []


    @api.model
    def _prepare_order_vals(self, order_data, order_items, cloud_id=None):
        vals = {
            'point_of_sale_dotykacka': str(order_data.get('branchid', '')),
            'check_number_dotykacka': order_data.get('orderseriesid', ''),
            'dotykacka_last_sync': fields.Datetime.now(),
        }

        employee_id = order_data.get('employeeid')

        if employee_id is not None:
            employee = self.env['hr.employee'].sudo().search([
                ('dotykachka_employee_id', '=', employee_id)
            ], limit=1)

            if employee:
                vals['user_id'] = employee.user_id.id
            else:
                _logger.warning(f"No user found for Dotykačka employee ID: {employee_id}")

        # Поиск или создание партнера
        partner = self._get_or_create_partner(order_data)
        vals['partner_id'] = partner.id

        status = order_data.get('status', 'open')
        if status == 'closed' and order_data.get('completed'):
            vals['state'] = 'sale'
        elif order_data.get('canceled_date'):
            vals['state'] = 'cancel'
        else:
            vals['state'] = 'draft'

        if order_data.get('note'):
            vals['note'] = order_data.get('note')

        order_lines = self._prepare_order_lines(order_items, cloud_id)
        if order_lines:
            vals['order_line'] = order_lines

        return vals

    # @api.model
    # def _prepare_order_lines(self, order_items):
    #     order_lines = []
    #     PT = self.env['product.template'].sudo()
    #
    #     for item in order_items:
    #         try:
    #             category_id = str(item.get('_categoryId', ''))
    #             product_id = item.get('_productId') or item.get('productId')
    #
    #             if not category_id:
    #                 _logger.warning(f"Item without category: {item}")
    #                 continue
    #
    #             # Поиск продукта по dotykachka_category_id
    #             product_tmpl = PT.search([
    #                 ('dotykachka_id', '=', product_id)
    #             ], limit=1)
    #
    #             if not product_tmpl:
    #                 _logger.warning(f"Product not found for category {category_id}")
    #                 continue
    #
    #             # Получение product.product
    #             product = product_tmpl.product_variant_ids[:1]
    #
    #             if not product:
    #                 _logger.warning(f"No product variant for template {product_tmpl.id}")
    #                 continue
    #
    #             quantity = float(item.get('quantity', 1))
    #             price = float(item.get('unitPriceWithoutVat', 0))
    #
    #             line_vals = {
    #                 'product_id': product.id,
    #                 'product_uom_qty': quantity,
    #                 'price_unit': price,
    #             }
    #
    #             if item.get('_name'):
    #                 line_vals['name'] = item['_name']
    #
    #             order_lines.append((0, 0, line_vals))
    #
    #         except Exception as e:
    #             _logger.error(f"Error preparing line for item {item.get('_id')}: {str(e)}")
    #             continue
    #
    #     return order_lines

    @api.model
    def _prepare_order_lines(self, order_items, cloud_id=None):
        """Создание строк заказа из элементов order-items API"""
        order_lines = []
        PT = self.env['product.template'].sudo()

        _logger.info(f"=== Processing {len(order_items)} items for order ===")

        for item in order_items:
            try:
                # Получаем _productId (может быть отрицательным!)
                product_id = str(item.get('_productId', ''))
                product_name = item.get('name', 'Unknown Product')

                if not product_id:
                    _logger.warning(f"Item without _productId: {item}")
                    continue

                _logger.info(f"Processing item: _productId={product_id}, name={product_name}, cloud_id={cloud_id}")

                # 🔍 Поиск продукта по dotykachka_id И cloud_id
                domain = [('dotykachka_id', '=', product_id)]
                if cloud_id:
                    domain.append(('dotykacka_cloud_id', '=', cloud_id))

                product_tmpl = PT.search(domain, limit=1)

                if not product_tmpl:
                    _logger.error(f"❌ Product NOT FOUND in Odoo: dotykachka_id={product_id}, name={product_name}")

                    # Проверим что вообще есть в базе
                    sample_products = PT.search([('dotykachka_id', '!=', False)], limit=3)
                    _logger.info(f"Sample products in DB: {[(p.dotykachka_id, p.name) for p in sample_products]}")

                    continue

                _logger.info(f"✅ Product FOUND: {product_tmpl.name} (dotykachka_id={product_tmpl.dotykachka_id})")

                # Получение product.product (варианта)
                product = product_tmpl.product_variant_ids[:1]

                if not product:
                    _logger.error(f"No product variant for template {product_tmpl.id}")
                    continue

                # Данные для строки заказа
                quantity = float(item.get('quantity', 1))
                price = float(item.get('unitPriceWithoutVat', 0))

                line_vals = {
                    'product_id': product.id,
                    'product_uom_qty': quantity,
                    'price_unit': price,
                }

                # Добавляем название если есть
                if item.get('name'):
                    line_vals['name'] = item['name']

                order_lines.append((0, 0, line_vals))
                _logger.info(f"✅ Order line created: product={product.name}, qty={quantity}, price={price}")

            except Exception as e:
                _logger.error(f"Error preparing line for item {item.get('id')}: {str(e)}", exc_info=True)
                continue

        _logger.info(f"=== Created {len(order_lines)} order lines ===")
        return order_lines

    @api.model
    def _get_or_create_partner(self, order_data):
        try:
            Partner = self.env['res.partner'].sudo()
            customer_long_id = order_data.get('customerlongid')

            if not customer_long_id:
                partner = Partner.search([
                    ('name', '=', 'Dotykačka Walk-in Customer')
                ], limit=1)

                if not partner:
                    partner = Partner.create({
                        'name': 'Dotykačka Walk-in Customer',
                        'customer_rank': 1,
                    })

                return partner

            partner = Partner.search([
                ('dotykachka_customer_id', '=', str(customer_long_id))
            ], limit=1)

            if partner:
                return partner

            customer_data = self._fetch_customer_from_api(customer_long_id)

            if not customer_data:
                partner = Partner.search([
                    ('name', '=', 'Dotykačka Walk-in Customer')
                ], limit=1)

                if not partner:
                    partner = Partner.create({
                        'name': 'Dotykačka Walk-in Customer',
                        'customer_rank': 1,
                    })

                return partner

            partner_vals = self._prepare_partner_vals(customer_data)
            partner = Partner.create(partner_vals)

            return partner

        except Exception as e:
            admin_user = self.env.ref('base.user_admin')
            return admin_user.partner_id

    @api.model
    def _fetch_customer_from_api(self, customer_long_id):
        try:
            ICP = self.env['ir.config_parameter'].sudo()
            api_token = ICP.get_param('dotykacka.api_token')
            cloud_id = ICP.get_param('dotykacka.cloud_id')

            if not api_token:
                _logger.error("Dotykačka API token not configured")
                return None

            url = f"https://api.dotykacka.cz/v2/clouds/{cloud_id}/customers"

            headers = {
                'Authorization': f'Bearer {api_token}',
                'Content-Type': 'application/json'
            }

            response = requests.get(url, headers=headers, timeout=30)

            if response.status_code != 200:
                _logger.error(f"API error {response.status_code}: {response.text}")
                return None

            response_data = response.json()
            all_customers = response_data.get('data', [])

            for idx, customer in enumerate(all_customers):
                customer_id = str(customer.get('id', ''))
                target_id = str(customer_long_id)

                if customer_id == target_id:
                    return customer
            return None

        except Exception as e:
            _logger.error(f"Error fetching customer: {str(e)}", exc_info=True)
            return None

    @api.model
    def _prepare_partner_vals(self, customer_data):

        first_name = (customer_data.get('firstName') or '').strip()
        last_name = (customer_data.get('lastName') or '').strip()
        company_name = (customer_data.get('companyName') or '').strip()

        if company_name:
            name = company_name
        elif first_name or last_name:
            name = f"{first_name} {last_name}".strip()
        else:
            name = f"Customer {customer_data.get('customerId', 'Unknown')}"

        vals = {
            'name': name,
            'customer_rank': 1,
            'dotykachka_customer_id': str(customer_data.get('id', '')),
        }

        if customer_data.get('email'):
            vals['email'] = customer_data['email']

        if customer_data.get('phone'):
            vals['phone'] = customer_data['phone']
        elif customer_data.get('cellPhone'):
            vals['phone'] = customer_data['cellPhone']

        if customer_data.get('cellPhone'):
            vals['mobile'] = customer_data['cellPhone']

        street_parts = []
        if customer_data.get('street'):
            street_parts.append(customer_data['addressLine1'])
        if customer_data.get('houseNumber'):
            street_parts.append(customer_data['houseNumber'])

        if street_parts:
            vals['street'] = ' '.join(street_parts)

        if customer_data.get('city'):
            vals['city'] = customer_data['city']

        if customer_data.get('zip'):
            vals['zip'] = customer_data['zip']

        if customer_data.get('vatNumber'):
            vals['vat'] = customer_data['vatNumber']

        if customer_data.get('vatNumber'):
            vals['vat'] = customer_data['vatNumber']

        if company_name:
            vals['company_type'] = 'company'
        else:
            vals['company_type'] = 'person'

        return vals
