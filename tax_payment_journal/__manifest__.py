{
    'name': 'Withholding Tax on Payments',
    'version': '0.1',
    'category': 'accouting',
    'license': "AGPL-3",
    'summary': " ",
    'author': 'Itech resources',
    'company': 'ItechResources',
    'depends': [
                'sale',
                'purchase',
                'account',
                ],
    'data': [

            'views/account_tax.xml',
            'views/payment_view.xml',
            
            ],
    'installable': True,
    'auto_install': False,
    'price':'80.0',
    'currency': 'EUR',
}
