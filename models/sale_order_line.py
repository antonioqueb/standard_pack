from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import math


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    # === Pack Selection Fields ===
    standard_pack_id = fields.Many2one(
        'standard.pack',
        string='Standard Pack',
        domain="[('product_tmpl_id', '=', product_template_id)]",
        help='Select the standard pack for this product',
    )
    pack_qty = fields.Float(
        string='# Packs',
        digits='Product Unit of Measure',
        help='Number of standard packs to sell',
    )
    qty_per_pack = fields.Float(
        string='Qty/Pack',
        related='standard_pack_id.qty_per_pack',
        readonly=True,
    )
    pack_type_name = fields.Char(
        string='Pack Type',
        related='standard_pack_id.pack_type_id.name',
        readonly=True,
    )

    # === Compliance Fields ===
    pack_status = fields.Selection(
        [
            ('compliant', 'Compliant'),
            ('non_compliant', 'Non-Compliant'),
            ('approved_exception', 'Approved Exception'),
            ('pending_exception', 'Pending Approval'),
            ('rejected_exception', 'Rejected'),
            ('no_pack', 'No Pack Defined'),
        ],
        string='Pack Status',
        compute='_compute_pack_status',
        store=True,
    )
    pack_status_message = fields.Char(
        string='Pack Note',
        compute='_compute_pack_status',
        store=True,
    )
    has_standard_pack = fields.Boolean(
        string='Has Standard Pack',
        related='product_template_id.has_standard_pack',
        readonly=True,
    )

    # === Exception Request ===
    exception_request_id = fields.Many2one(
        'pack.exception.request',
        string='Exception Request',
        readonly=True,
        copy=False,
    )
    exception_state = fields.Selection(
        related='exception_request_id.state',
        string='Exception State',
        readonly=True,
    )

    @api.depends(
        'product_template_id',
        'product_uom_qty',
        'standard_pack_id',
        'pack_qty',
        'exception_request_id',
        'exception_request_id.state',
    )
    def _compute_pack_status(self):
        for line in self:
            if line.display_type or not line.product_template_id:
                line.pack_status = False
                line.pack_status_message = False
                continue

            if not line.product_template_id.has_standard_pack:
                line.pack_status = 'no_pack'
                line.pack_status_message = ''
                continue

            if not line.standard_pack_id:
                if line.product_uom_qty:
                    line.pack_status = 'non_compliant'
                    line.pack_status_message = _('No pack selected — select a standard pack')
                else:
                    line.pack_status = 'no_pack'
                    line.pack_status_message = ''
                continue

            expected_qty = line.pack_qty * line.standard_pack_id.qty_per_pack
            is_exact_multiple = (
                line.product_uom_qty
                and abs(line.product_uom_qty - expected_qty) < 0.001
            )

            if is_exact_multiple:
                line.pack_status = 'compliant'
                line.pack_status_message = _(
                    '%(packs)s × %(qty)s = %(total)s %(uom)s',
                    packs=f"{line.pack_qty:g}",
                    qty=f"{line.standard_pack_id.qty_per_pack:g}",
                    total=f"{line.product_uom_qty:g}",
                    uom=line.product_uom.name or '',
                )
            elif line.exception_request_id:
                exc_state = line.exception_request_id.state
                if exc_state == 'approved':
                    line.pack_status = 'approved_exception'
                    line.pack_status_message = _(
                        'Approved by %s',
                        line.exception_request_id.approver_id.name or '',
                    )
                elif exc_state == 'pending':
                    line.pack_status = 'pending_exception'
                    line.pack_status_message = _('Waiting for approval')
                elif exc_state == 'rejected':
                    line.pack_status = 'rejected_exception'
                    reason = line.exception_request_id.rejection_reason or ''
                    line.pack_status_message = _(
                        'Rejected: %s', reason[:80],
                    )
            else:
                line.pack_status = 'non_compliant'
                nearest = self._get_nearest_pack_qty(line)
                line.pack_status_message = _(
                    'Non-standard: %(qty)s %(uom)s (nearest: %(near)s)',
                    qty=f"{line.product_uom_qty:g}",
                    uom=line.product_uom.name or '',
                    near=f"{nearest:g}",
                )

    def _get_nearest_pack_qty(self, line):
        """Get the nearest valid standard pack total quantity."""
        if not line.standard_pack_id or not line.standard_pack_id.qty_per_pack:
            return line.product_uom_qty
        pack_size = line.standard_pack_id.qty_per_pack
        packs_lower = math.floor(line.product_uom_qty / pack_size)
        packs_upper = math.ceil(line.product_uom_qty / pack_size)
        qty_lower = packs_lower * pack_size
        qty_upper = packs_upper * pack_size
        if abs(line.product_uom_qty - qty_lower) <= abs(line.product_uom_qty - qty_upper):
            return qty_lower if qty_lower > 0 else qty_upper
        return qty_upper

    @api.onchange('standard_pack_id')
    def _onchange_standard_pack_id(self):
        if self.standard_pack_id:
            if not self.pack_qty:
                self.pack_qty = 1
            self.product_uom_qty = self.pack_qty * self.standard_pack_id.qty_per_pack
        elif self.has_standard_pack:
            self.pack_qty = 0

    @api.onchange('pack_qty')
    def _onchange_pack_qty(self):
        if self.standard_pack_id and self.pack_qty:
            self.product_uom_qty = self.pack_qty * self.standard_pack_id.qty_per_pack

    @api.onchange('product_id')
    def _onchange_product_id_set_pack(self):
        if self.product_template_id and self.product_template_id.has_standard_pack:
            default_pack = self.product_template_id.default_pack_id
            if default_pack:
                self.standard_pack_id = default_pack
                self.pack_qty = 1
                self.product_uom_qty = default_pack.qty_per_pack

    @api.onchange('product_uom_qty')
    def _onchange_product_uom_qty_check_pack(self):
        if (
            self.standard_pack_id
            and self.product_uom_qty
            and self.standard_pack_id.qty_per_pack
        ):
            pack_size = self.standard_pack_id.qty_per_pack
            packs = self.product_uom_qty / pack_size
            if abs(packs - round(packs)) < 0.001:
                self.pack_qty = round(packs)

    def _check_pack_restriction(self):
        """
        Validate pack compliance based on user permission level.
        Called before confirming the sale order.
        """
        user = self.env.user
        is_unrestricted = user.has_group(
            'standard_pack.group_standard_pack_unrestricted'
        )

        for line in self:
            if line.display_type or not line.product_template_id.has_standard_pack:
                continue

            if line.pack_status in ('compliant', 'no_pack', 'approved_exception'):
                continue

            if line.pack_status == 'pending_exception':
                raise ValidationError(_(
                    'Line "%(product)s": Exception request is pending approval. '
                    'Cannot confirm until approved.',
                    product=line.product_id.display_name,
                ))

            if line.pack_status == 'rejected_exception':
                raise ValidationError(_(
                    'Line "%(product)s": Exception was rejected. '
                    'Adjust the quantity or submit a new request.',
                    product=line.product_id.display_name,
                ))

            # non_compliant without exception
            if not is_unrestricted:
                raise ValidationError(_(
                    'Line "%(product)s": Quantity %(qty)s does not match '
                    'the standard pack (%(pack)s). '
                    'Request an exception before confirming.',
                    product=line.product_id.display_name,
                    qty=f"{line.product_uom_qty:g}",
                    pack=line.standard_pack_id.display_name or 'N/A',
                ))

    def action_request_pack_exception(self):
        """Open wizard to create exception request with reason."""
        self.ensure_one()

        # If already has a request, open it
        if self.exception_request_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'pack.exception.request',
                'res_id': self.exception_request_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

        # Open the request wizard
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'pack.exception.request.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.order_id.id,
                'default_sale_line_id': self.id,
                'default_product_id': self.product_id.id,
                'default_standard_pack_id': self.standard_pack_id.id if self.standard_pack_id else False,
                'default_requested_qty': self.product_uom_qty,
                'default_pack_compliant_qty': self._get_nearest_pack_qty(self),
            },
        }

    def action_reset_exception(self):
        """Clear rejected exception so user can re-request."""
        self.ensure_one()
        if self.exception_request_id and self.exception_request_id.state == 'rejected':
            self.exception_request_id = False