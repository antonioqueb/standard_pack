from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    standard_pack_ids = fields.One2many(
        'standard.pack',
        'product_tmpl_id',
        string='Standard Packs',
    )
    standard_pack_count = fields.Integer(
        string='Pack Count',
        compute='_compute_standard_pack_count',
    )
    has_standard_pack = fields.Boolean(
        string='Has Standard Pack',
        compute='_compute_standard_pack_count',
        store=True,
        help='Indicates if this product has at least one standard pack defined',
    )
    default_pack_id = fields.Many2one(
        'standard.pack',
        string='Default Standard Pack',
        compute='_compute_default_pack',
        store=True,
    )

    @api.depends('standard_pack_ids', 'standard_pack_ids.active')
    def _compute_standard_pack_count(self):
        for product in self:
            packs = product.standard_pack_ids.filtered('active')
            product.standard_pack_count = len(packs)
            product.has_standard_pack = bool(packs)

    @api.depends('standard_pack_ids.is_default', 'standard_pack_ids.active')
    def _compute_default_pack(self):
        for product in self:
            default = product.standard_pack_ids.filtered(
                lambda p: p.is_default and p.active
            )
            product.default_pack_id = default[:1] if default else False
