# pylama:ignore=C0114,D100
{
    'name': 'API Management',
    'summary': 'This module provides management for Endpoints and Outgoing API Requests.',
    'author': 'GymBeam',
    'license': 'AGPL-3',
    'website': 'https://www.gymbeam.com',
    'category': 'API',
    'version': '18.0.0.1.0',
    # any module necessary for this one to work correctly
    'depends': ['base'],
    # always loaded
    'data': [
        # Security
        'security/security.xml',
        'security/ir.model.access.csv',
        #Data
        'data/providers.xml',
        'data/requests.xml',
        # Views
        'views/provider.xml',
        'views/request.xml',
        'views/request_parameter.xml',
        'views/logger.xml',
        # Menu Items
        'views/actions.xml',
        'views/menu_items.xml',
    ],
    # only loaded in demonstration mode
    'demo': [],
}
