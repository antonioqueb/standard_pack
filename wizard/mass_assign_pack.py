from odoo import models, fields, api, _


class PackExceptionRequestWizard(models.TransientModel):
    """Wizard to create an exception request with a reason."""
    _name = 'pack.exception.request.wizard'
    _description = 'Request Pack Exception'

    sale_order_id = fields.Many2one('sale.order', string='Sale Order', readonly=True)
    sale_line_id = fields.Many2one('sale.order.line', string='Order Line', readonly=True)
    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    standard_pack_id = fields.Many2one('standard.pack', string='Standard Pack', readonly=True)
    requested_qty = fields.Float(string='Requested Quantity', readonly=True, digits='Product Unit of Measure')
    pack_compliant_qty = fields.Float(string='Nearest Standard Qty', readonly=True, digits='Product Unit of Measure')
    reason = fields.Text(
        string='Reason',
        required=True,
        help='Explain why a non-standard quantity is needed',
    )

    def action_submit_request(self):
        self.ensure_one()
        line = self.sale_line_id

        # Create the exception request
        request = self.env['pack.exception.request'].create({
            'sale_order_id': self.sale_order_id.id,
            'sale_line_id': line.id,
            'product_id': self.product_id.id,
            'standard_pack_id': self.standard_pack_id.id if self.standard_pack_id else False,
            'requested_qty': self.requested_qty,
            'pack_compliant_qty': self.pack_compliant_qty,
            'requester_id': self.env.user.id,
            'reason': self.reason,
        })

        # Link to the sale order line
        line.write({'exception_request_id': request.id})

        # Notify approvers
        request._notify_approvers()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Exception Request Submitted'),
                'message': _(
                    'Your request for %(product)s has been submitted. '
                    'Approvers have been notified.',
                    product=self.product_id.display_name,
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class MassAssignPack(models.TransientModel):
    _name = 'mass.assign.pack.wizard'
    _description = 'Mass Assign Standard Pack'

    pack_type_id = fields.Many2one(
        'standard.pack.type',
        string='Pack Type',
        required=True,
    )
    qty_per_pack = fields.Float(
        string='Qty per Pack',
        required=True,
        digits='Product Unit of Measure',
    )
    is_default = fields.Boolean(
        string='Set as Default',
        default=True,
    )
    product_tmpl_ids = fields.Many2many(
        'product.template',
        string='Products',
        help='Leave empty to apply to all selected products from the list',
    )
    overwrite_existing = fields.Boolean(
        string='Overwrite Existing',
        default=False,
        help='If checked, existing packs with the same type will be updated',
    )
    preview_count = fields.Integer(
        string='Products to Update',
        compute='_compute_preview_count',
    )

    @api.depends('product_tmpl_ids')
    def _compute_preview_count(self):
        for wiz in self:
            if wiz.product_tmpl_ids:
                wiz.preview_count = len(wiz.product_tmpl_ids)
            else:
                wiz.preview_count = len(
                    self.env.context.get('active_ids', [])
                )

    def action_assign(self):
        self.ensure_one()
        product_ids = self.product_tmpl_ids or self.env['product.template'].browse(
            self.env.context.get('active_ids', [])
        )

        created = 0
        updated = 0

        for product in product_ids:
            existing = self.env['standard.pack'].search([
                ('product_tmpl_id', '=', product.id),
                ('pack_type_id', '=', self.pack_type_id.id),
                ('qty_per_pack', '=', self.qty_per_pack),
            ], limit=1)

            if existing:
                if self.overwrite_existing:
                    existing.write({'is_default': self.is_default})
                    updated += 1
                continue

            if self.overwrite_existing:
                old_packs = self.env['standard.pack'].search([
                    ('product_tmpl_id', '=', product.id),
                    ('pack_type_id', '=', self.pack_type_id.id),
                ])
                old_packs.unlink()

            if self.is_default:
                product.standard_pack_ids.filtered('is_default').write(
                    {'is_default': False}
                )

            self.env['standard.pack'].create({
                'product_tmpl_id': product.id,
                'pack_type_id': self.pack_type_id.id,
                'qty_per_pack': self.qty_per_pack,
                'is_default': self.is_default,
            })
            created += 1

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mass Pack Assignment Complete'),
                'message': _(
                    '%(created)s packs created, %(updated)s updated.',
                    created=created,
                    updated=updated,
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }


class PackExceptionRejectWizard(models.TransientModel):
    _name = 'pack.exception.reject.wizard'
    _description = 'Reject Pack Exception'

    request_id = fields.Many2one(
        'pack.exception.request',
        string='Request',
        required=True,
    )
    rejection_reason = fields.Text(
        string='Rejection Reason',
        required=True,
    )

    def action_confirm_reject(self):
        self.ensure_one()
        self.request_id.write({
            'state': 'rejected',
            'approver_id': self.env.user.id,
            'rejection_reason': self.rejection_reason,
        })
        # Mark activities as done
        self.request_id.activity_ids.action_done()
        # Notify requester
        self.request_id._notify_requester('rejected')
        # Recompute line status
        self.request_id.sale_line_id._compute_pack_status()
        return {'type': 'ir.actions.act_window_close'}