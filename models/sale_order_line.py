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
    exception_approved = fields.Boolean(
        string='Exception Approved',
        compute='_compute_exception_approved',
        store=True,
    )

    @api.depends('exception_request_id', 'exception_request_id.state')
    def _compute_exception_approved(self):
        for line in self:
            line.exception_approved = (
                line.exception_request_id
                and line.exception_request_id.state == 'approved'
            )

    @api.depends(
        'product_template_id',
        'product_uom_qty',
        'standard_pack_id',
        'pack_qty',
        'exception_approved',
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
            if line.product_uom_qty and abs(line.product_uom_qty - expected_qty) < 0.001:
                line.pack_status = 'compliant'
                line.pack_status_message = _(
                    '%(packs)s × %(qty)s = %(total)s %(uom)s',
                    packs=f"{line.pack_qty:g}",
                    qty=f"{line.standard_pack_id.qty_per_pack:g}",
                    total=f"{line.product_uom_qty:g}",
                    uom=line.product_uom.name or '',
                )
            elif line.exception_approved:
                line.pack_status = 'approved_exception'
                line.pack_status_message = _('Non-standard qty approved')
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
        """When selecting a pack, reset pack qty to 1 and compute total."""
        if self.standard_pack_id:
            if not self.pack_qty:
                self.pack_qty = 1
            self.product_uom_qty = self.pack_qty * self.standard_pack_id.qty_per_pack
        elif self.has_standard_pack:
            self.pack_qty = 0

    @api.onchange('pack_qty')
    def _onchange_pack_qty(self):
        """Recalculate product_uom_qty based on pack qty."""
        if self.standard_pack_id and self.pack_qty:
            self.product_uom_qty = self.pack_qty * self.standard_pack_id.qty_per_pack

    @api.onchange('product_id')
    def _onchange_product_id_set_pack(self):
        """Auto-select default pack when product changes."""
        if self.product_template_id and self.product_template_id.has_standard_pack:
            default_pack = self.product_template_id.default_pack_id
            if default_pack:
                self.standard_pack_id = default_pack
                self.pack_qty = 1
                self.product_uom_qty = default_pack.qty_per_pack

    @api.onchange('product_uom_qty')
    def _onchange_product_uom_qty_check_pack(self):
        """Check if manually entered qty matches a pack multiple."""
        if (
            self.standard_pack_id
            and self.product_uom_qty
            and self.standard_pack_id.qty_per_pack
        ):
            pack_size = self.standard_pack_id.qty_per_pack
            packs = self.product_uom_qty / pack_size
            if abs(packs - round(packs)) < 0.001:
                self.pack_qty = round(packs)
            else:
                # Don't reset pack_qty, let the status show non-compliant
                pass

    def _check_pack_restriction(self):
        """
        Validate pack compliance based on user permission level.
        Called before confirming the sale order.
        """
        restricted_group = self.env.ref(
            'standard_pack.group_standard_pack_restricted', raise_if_not_found=False
        )
        unrestricted_group = self.env.ref(
            'standard_pack.group_standard_pack_unrestricted', raise_if_not_found=False
        )

        user = self.env.user
        is_unrestricted = unrestricted_group and user.has_group(
            'standard_pack.group_standard_pack_unrestricted'
        )
        is_restricted = restricted_group and user.has_group(
            'standard_pack.group_standard_pack_restricted'
        )

        for line in self:
            if line.display_type or not line.product_template_id.has_standard_pack:
                continue
            if line.pack_status in ('compliant', 'no_pack', 'approved_exception'):
                continue

            # Non-compliant line found
            if is_restricted:
                raise ValidationError(_(
                    'Line "%(product)s": The quantity %(qty)s does not match '
                    'any standard pack. You must request an exception before '
                    'confirming this order.',
                    product=line.product_id.display_name,
                    qty=f"{line.product_uom_qty:g}",
                ))
            elif not is_unrestricted:
                # Standard user — also blocked but with different message
                raise ValidationError(_(
                    'Line "%(product)s": Non-standard quantity %(qty)s. '
                    'Please request an exception or adjust to a standard pack.',
                    product=line.product_id.display_name,
                    qty=f"{line.product_uom_qty:g}",
                ))
            # Unrestricted user — allowed but status stays as warning

    def action_request_pack_exception(self):
        """Create an exception request for non-standard quantity."""
        self.ensure_one()
        if self.exception_request_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'pack.exception.request',
                'res_id': self.exception_request_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

        request = self.env['pack.exception.request'].create({
            'sale_order_id': self.order_id.id,
            'sale_line_id': self.id,
            'product_id': self.product_id.id,
            'standard_pack_id': self.standard_pack_id.id,
            'requested_qty': self.product_uom_qty,
            'pack_compliant_qty': self._get_nearest_pack_qty(self),
            'requester_id': self.env.user.id,
        })
        self.exception_request_id = request
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'pack.exception.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }
