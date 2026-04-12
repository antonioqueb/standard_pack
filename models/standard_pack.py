from odoo import models, fields, api


class StandardPack(models.Model):
    _name = 'standard.pack'
    _description = 'Standard Pack Definition'
    _order = 'product_tmpl_id, sequence'
    _rec_name = 'display_name'

    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product',
        required=True,
        ondelete='cascade',
        index=True,
    )
    pack_type_id = fields.Many2one(
        'standard.pack.type',
        string='Pack Type',
        required=True,
        ondelete='restrict',
    )
    qty_per_pack = fields.Float(
        string='Qty per Pack',
        required=True,
        digits='Product Unit of Measure',
        help='Number of units/pieces per standard pack',
    )
    uom_id = fields.Many2one(
        'uom.uom',
        string='Unit of Measure',
        related='product_tmpl_id.uom_id',
        store=True,
        readonly=True,
    )
    is_default = fields.Boolean(
        string='Default Pack',
        default=False,
        help='If checked, this pack will be pre-selected on sale order lines',
    )
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
    )

    @api.depends('pack_type_id.name', 'qty_per_pack', 'product_tmpl_id.name', 'uom_id.name')
    def _compute_display_name(self):
        for rec in self:
            if rec.pack_type_id and rec.qty_per_pack:
                rec.display_name = f"{rec.pack_type_id.name} x {rec.qty_per_pack:g} {rec.uom_id.name or ''}"
            else:
                rec.display_name = 'New'

    _sql_constraints = [
        ('qty_positive', 'CHECK(qty_per_pack > 0)',
         'The quantity per pack must be greater than zero!'),
        ('product_type_qty_uniq',
         'unique(product_tmpl_id, pack_type_id, qty_per_pack, company_id)',
         'A standard pack with the same type and quantity already exists for this product!'),
    ]
