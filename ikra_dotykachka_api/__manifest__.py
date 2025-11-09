{
    'name': 'Ikra Dotykachka Webhook Integration',
    'version': '18.0.1.0.0',
    'category': 'Integration',
    'summary': 'Ikra Webhook integration with Dotykachka',
    'description': """
        This module provides webhook endpoint to receive data from Dotykachka
    """,
    'author': '',
    'website': '',

    'depends': [
        'base',
        'sale',
        'api_manager',
        'key_crm_api',
        'hr'
    ],

    'data': [
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        #Views
        'views/product_priduct_view.xml',
        'views/product_priduct_view.xml',
        'views/res_partner_views.xml',
        'views/employees_view.xml',
        'views/res_config_settings_views.xml',
    ],

    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}