{
    'name': 'Standard Pack',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Define and enforce standard packaging quantities per product on sales orders',
    'description': """
        Standard Pack Module
        ====================
        - Define standard pack configurations per product (pallet, box, bundle, etc.)
        - Enforce pack-based selling on sale order lines
        - Three permission levels: Restricted, Standard, Unrestricted
        - Approval workflow for non-standard quantities
        - Mass assignment of standard packs to products
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'product',
        'stock',
        'mail',
    ],
    'data': [
        'security/standard_pack_security.xml',
        'security/ir.model.access.csv',
        'data/pack_type_data.xml',
        'views/pack_type_views.xml',
        'views/standard_pack_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/pack_exception_request_views.xml',
        'wizard/mass_assign_pack_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
