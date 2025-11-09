from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class DotykackaCloudConfig(models.Model):
    _name = 'dotykacka.cloud.config'
    _description = 'Dotykacka Cloud Configuration'
    _order = 'name'

    name = fields.Char(string='Cloud Name', required=True, help='Название облака для идентификации')
    cloud_id = fields.Char(string='Cloud ID', required=True, help='ID облака в Dotykacka')
    api_token = fields.Char(string='API Token', help='Текущий токен доступа к API')
    api_user_token = fields.Char(string='User API Token', required=True, help='Токен пользователя для обновления')
    active = fields.Boolean(string='Active', default=True, help='Активно ли это облако')
    last_token_refresh = fields.Datetime(string='Last Token Refresh', readonly=True)

    _sql_constraints = [
        ('cloud_id_unique', 'unique(cloud_id)', 'Cloud ID должен быть уникальным!')
    ]

    def refresh_token(self):
        """Обновить токен для этого облака"""
        self.ensure_one()
        try:
            # Находим провайдера для обновления токена
            provider = self.env.ref('api_manager.provider_dotykacka_get_accesstoken', raise_if_not_found=False)
            if not provider:
                _logger.error("Dotykacka provider for token refresh not found")
                return False

            # Временно устанавливаем credentials для этого облака
            old_value = provider.value
            provider.sudo().write({'value': f'User {self.api_user_token}'})

            try:
                # Отправляем запрос на обновление токена
                request = self.env.ref('api_manager.api_request_dotykacka_refresh_token')
                if not request:
                    _logger.error("Dotykacka refresh token request not found")
                    return False

                request.send_request()

                # Получаем ответ
                if hasattr(request, 'response') and request.response:
                    response_data = request.response.json()
                    new_token = response_data.get('accessToken') or response_data.get('token')

                    if new_token:
                        self.write({
                            'api_token': new_token,
                            'last_token_refresh': fields.Datetime.now()
                        })
                        _logger.info(f"Token refreshed successfully for cloud {self.name} (ID: {self.cloud_id})")
                        return True
                    else:
                        _logger.warning(f"Token not found in response for cloud {self.name}")
                        return False
                else:
                    _logger.warning(f"No response received for cloud {self.name}")
                    return False

            finally:
                # Восстанавливаем оригинальные credentials провайдера
                provider.sudo().write({'value': old_value})

        except Exception as e:
            _logger.error(f"Error refreshing token for cloud {self.name}: {e}")
            import traceback
            traceback.print_exc()
            return False

    @api.model
    def cron_refresh_all_tokens(self):
        """Обновить токены для всех активных облаков"""
        clouds = self.search([('active', '=', True)])
        for cloud in clouds:
            try:
                cloud.refresh_token()
            except Exception as e:
                _logger.error(f"Error refreshing token for cloud {cloud.name}: {e}")
                continue
