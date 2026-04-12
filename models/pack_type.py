from odoo import models, fields


class PackType(models.Model):
    _name = 'standard.pack.type'
    _description = 'Pack Type'
    _order = 'sequence, name'

    name = fields.Char(string='Name', required=True, translate=True)
    code = fields.Char(string='Code', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(string='Description', translate=True)
    icon = fields.Char(
        string='Icon',
        help='CSS class for the icon (e.g., fa-cubes, fa-archive)',
        default='fa-cube',
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The pack type code must be unique!'),
    ]
