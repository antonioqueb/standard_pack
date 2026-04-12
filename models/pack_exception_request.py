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
        required=True, tracking=True,
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
            rec.display_name = (
                f"EXC/{rec.sale_order_id.name or 'New'}"
                f"/{rec.product_id.display_name or ''}"
            )

    @api.depends('requested_qty', 'pack_compliant_qty')
    def _compute_difference(self):
        for rec in self:
            rec.difference = rec.requested_qty - rec.pack_compliant_qty

    def _get_approver_users(self):
        """Get all users in the approver group."""
        approver_group = self.env.ref(
            'standard_pack.group_standard_pack_approver',
            raise_if_not_found=False,
        )
        if approver_group:
            return approver_group.users
        return self.env['res.users']

    def _notify_approvers(self):
        """Send notification to all approvers about new request."""
        self.ensure_one()
        approvers = self._get_approver_users()
        if not approvers:
            return

        # Add approvers as followers
        partner_ids = approvers.mapped('partner_id').ids
        self.message_subscribe(partner_ids=partner_ids)

        # Post notification
        self.message_post(
            body=_(
                '<strong>New exception request</strong><br/>'
                '<b>Requester:</b> %(user)s<br/>'
                '<b>Order:</b> %(order)s<br/>'
                '<b>Product:</b> %(product)s<br/>'
                '<b>Requested qty:</b> %(qty)s (Standard pack: %(std)s)<br/>'
                '<b>Reason:</b> %(reason)s',
                user=self.requester_id.name,
                order=self.sale_order_id.name,
                product=self.product_id.display_name,
                qty=f"{self.requested_qty:g}",
                std=self.standard_pack_id.display_name or 'N/A',
                reason=self.reason or '',
            ),
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
            partner_ids=partner_ids,
        )

        # Create activity for each approver
        for approver in approvers:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=approver.id,
                summary=_(
                    'Pack exception: %(product)s — %(order)s',
                    product=self.product_id.display_name,
                    order=self.sale_order_id.name,
                ),
                note=_(
                    '%(user)s requests to sell %(qty)s of %(product)s '
                    '(standard pack: %(std)s). Reason: %(reason)s',
                    user=self.requester_id.name,
                    qty=f"{self.requested_qty:g}",
                    product=self.product_id.display_name,
                    std=self.standard_pack_id.display_name or 'N/A',
                    reason=self.reason or '',
                ),
            )

    def _notify_requester(self, action_type):
        """Notify the requester about approval/rejection."""
        self.ensure_one()
        partner_id = self.requester_id.partner_id.id

        if action_type == 'approved':
            body = _(
                '<strong>Exception APPROVED</strong><br/>'
                '<b>Approved by:</b> %(approver)s<br/>'
                '<b>Order:</b> %(order)s<br/>'
                '<b>Product:</b> %(product)s — %(qty)s units<br/>'
                'You can now confirm the sale order.',
                approver=self.env.user.name,
                order=self.sale_order_id.name,
                product=self.product_id.display_name,
                qty=f"{self.requested_qty:g}",
            )
        else:
            body = _(
                '<strong>Exception REJECTED</strong><br/>'
                '<b>Rejected by:</b> %(approver)s<br/>'
                '<b>Order:</b> %(order)s<br/>'
                '<b>Product:</b> %(product)s — %(qty)s units<br/>'
                '<b>Reason:</b> %(reason)s<br/>'
                'Please adjust the quantity to a standard pack.',
                approver=self.env.user.name,
                order=self.sale_order_id.name,
                product=self.product_id.display_name,
                qty=f"{self.requested_qty:g}",
                reason=self.rejection_reason or '',
            )

        self.message_post(
            body=body,
            message_type='notification',
            subtype_xmlid='mail.mt_comment',
            partner_ids=[partner_id],
        )

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('standard_pack.group_standard_pack_approver'):
            raise UserError(_('You do not have permission to approve exception requests.'))
        self.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
        })
        # Mark activities as done
        self.activity_ids.action_done()
        # Notify requester
        self._notify_requester('approved')
        # Recompute line status
        self.sale_line_id._compute_pack_status()

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
        self._notify_approvers()

    def action_open_sale_order(self):
        """Quick action to open the related sale order."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }