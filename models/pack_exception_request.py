from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PackExceptionRequest(models.Model):
    _name = 'pack.exception.request'
    _description = 'Standard Pack Exception Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    display_name = fields.Char(
        compute='_compute_display_name', store=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order', string='Sale Order',
        required=True, ondelete='cascade', readonly=True,
    )
    sale_line_id = fields.Many2one(
        'sale.order.line', string='Sale Order Line',
        required=True, ondelete='cascade', readonly=True,
    )
    product_id = fields.Many2one(
        'product.product', string='Product',
        required=True, readonly=True,
    )
    standard_pack_id = fields.Many2one(
        'standard.pack', string='Standard Pack',
        readonly=True,
    )
    pack_type_name = fields.Char(
        related='standard_pack_id.pack_type_id.name',
        string='Pack Type',
    )
    qty_per_pack = fields.Float(
        related='standard_pack_id.qty_per_pack',
        string='Standard Qty/Pack',
    )

    requested_qty = fields.Float(
        string='Requested Quantity',
        required=True, readonly=True,
        digits='Product Unit of Measure',
    )
    pack_compliant_qty = fields.Float(
        string='Nearest Standard Qty',
        readonly=True,
        digits='Product Unit of Measure',
        help='The nearest quantity that would comply with the standard pack',
    )
    difference = fields.Float(
        string='Difference',
        compute='_compute_difference',
        digits='Product Unit of Measure',
    )

    requester_id = fields.Many2one(
        'res.users', string='Requested By',
        required=True, readonly=True,
        default=lambda self: self.env.user,
    )
    approver_id = fields.Many2one(
        'res.users', string='Approved/Rejected By',
        readonly=True, tracking=True,
    )
    reason = fields.Text(
        string='Reason for Exception',
        tracking=True,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True, tracking=True,
    )
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id',
        string='Customer', store=True,
    )

    state = fields.Selection(
        [
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Status', default='pending',
        required=True, tracking=True,
    )

    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )

    @api.depends('product_id.display_name', 'sale_order_id.name')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"EXC/{rec.sale_order_id.name or 'New'}/{rec.product_id.display_name or ''}"

    @api.depends('requested_qty', 'pack_compliant_qty')
    def _compute_difference(self):
        for rec in self:
            rec.difference = rec.requested_qty - rec.pack_compliant_qty

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('standard_pack.group_standard_pack_approver'):
            raise UserError(_('You do not have permission to approve exception requests.'))
        self.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
        })
        self.sale_line_id._compute_pack_status()
        self.message_post(
            body=_('Exception request approved by %s', self.env.user.display_name),
            message_type='notification',
        )

    def action_reject(self):
        self.ensure_one()
        if not self.env.user.has_group('standard_pack.group_standard_pack_approver'):
            raise UserError(_('You do not have permission to reject exception requests.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'pack.exception.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def action_reset_to_pending(self):
        self.ensure_one()
        self.write({
            'state': 'pending',
            'approver_id': False,
            'rejection_reason': False,
        })
        self.sale_line_id._compute_pack_status()
