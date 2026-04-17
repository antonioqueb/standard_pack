from markupsafe import Markup, escape
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
        approver_group = self.env.ref(
            'standard_pack.group_standard_pack_approver',
            raise_if_not_found=False,
        )
        if approver_group:
            return approver_group.users
        return self.env['res.users']

    def _post_comment_no_autofollow(self, target_record, body):
        """Post in chatter without creating followers automatically."""
        if not target_record or not target_record.id:
            return
        target_record.with_context(
            mail_post_autofollow=False,
            mail_create_nosubscribe=True,
            mail_notify_force_send=False,
        ).message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

    def _create_todo_activity_once(self, target_record, user, summary, note):
        """Create a todo activity without using activity_schedule/autofollow."""
        if not target_record or not target_record.id or not user:
            return

        activity_type = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        if not activity_type:
            return

        model = self.env['ir.model']._get(target_record._name)
        if not model:
            return

        deadline = fields.Date.context_today(self)

        existing = self.env['mail.activity'].search([
            ('res_model_id', '=', model.id),
            ('res_id', '=', target_record.id),
            ('user_id', '=', user.id),
            ('activity_type_id', '=', activity_type.id),
            ('summary', '=', summary),
            ('date_deadline', '=', deadline),
        ], limit=1)

        if existing:
            return

        self.env['mail.activity'].create({
            'activity_type_id': activity_type.id,
            'res_model_id': model.id,
            'res_id': target_record.id,
            'user_id': user.id,
            'summary': summary,
            'note': note,
            'date_deadline': deadline,
        })

    def _notify_approvers(self):
        """Notify approvers on the exception request without touching followers."""
        self.ensure_one()
        approvers = self._get_approver_users()
        if not approvers:
            return

        body = Markup(
            '<strong>Nueva solicitud de excepción</strong><br/>'
            '<b>Solicitante:</b> {user}<br/>'
            '<b>Orden:</b> {order}<br/>'
            '<b>Producto:</b> {product}<br/>'
            '<b>Cantidad solicitada:</b> {qty} (Pack estándar: {std})<br/>'
            '<b>Motivo:</b> {reason}'
        ).format(
            user=escape(self.requester_id.name),
            order=escape(self.sale_order_id.name),
            product=escape(self.product_id.display_name),
            qty=f"{self.requested_qty:g}",
            std=escape(self.standard_pack_id.display_name or 'N/A'),
            reason=escape(self.reason or ''),
        )

        self._post_comment_no_autofollow(self, body)

        for approver in approvers:
            self._create_todo_activity_once(
                self,
                approver,
                _('Excepción pack: %s — %s',
                  self.product_id.display_name,
                  self.sale_order_id.name),
                _('%s solicita vender %s de %s (pack estándar: %s). Motivo: %s',
                  self.requester_id.name,
                  f"{self.requested_qty:g}",
                  self.product_id.display_name,
                  self.standard_pack_id.display_name or 'N/A',
                  self.reason or ''),
            )

    def _notify_requester(self, action_type):
        """Notify requester on sale order without subscribing followers."""
        self.ensure_one()

        if action_type == 'approved':
            body = Markup(
                '<strong>✅ Excepción de pack aprobada</strong><br/>'
                '<b>Producto:</b> {product}<br/>'
                '<b>Cantidad:</b> {qty} aprobada por {approver}<br/>'
                'Ya puedes confirmar esta orden.'
            ).format(
                product=escape(self.product_id.display_name),
                qty=f"{self.requested_qty:g}",
                approver=escape(self.env.user.name),
            )
            summary = _('Excepción aprobada — confirmar orden')
            note = _('La excepción para %s (%s uds) fue aprobada. Puedes confirmar la orden.',
                     self.product_id.display_name,
                     f"{self.requested_qty:g}")
        else:
            body = Markup(
                '<strong>❌ Excepción de pack rechazada</strong><br/>'
                '<b>Producto:</b> {product}<br/>'
                '<b>Cantidad:</b> {qty} rechazada por {approver}<br/>'
                '<b>Motivo:</b> {reason}<br/>'
                'Ajusta la cantidad a un pack estándar.'
            ).format(
                product=escape(self.product_id.display_name),
                qty=f"{self.requested_qty:g}",
                approver=escape(self.env.user.name),
                reason=escape(self.rejection_reason or ''),
            )
            summary = _('Excepción rechazada — ajustar cantidad')
            note = _('La excepción para %s (%s uds) fue rechazada. Motivo: %s',
                     self.product_id.display_name,
                     f"{self.requested_qty:g}",
                     self.rejection_reason or '')

        self._post_comment_no_autofollow(self.sale_order_id, body)
        self._create_todo_activity_once(
            self.sale_order_id,
            self.requester_id,
            summary,
            note,
        )

    def action_approve(self):
        self.ensure_one()
        if not self.env.user.has_group('standard_pack.group_standard_pack_approver'):
            raise UserError(_('No tienes permisos para aprobar solicitudes de excepción.'))
        self.write({
            'state': 'approved',
            'approver_id': self.env.user.id,
        })
        self.activity_ids.action_done()
        self._notify_requester('approved')
        self.sale_line_id._compute_pack_status()

    def action_reject(self):
        self.ensure_one()
        if not self.env.user.has_group('standard_pack.group_standard_pack_approver'):
            raise UserError(_('No tienes permisos para rechazar solicitudes de excepción.'))
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
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }