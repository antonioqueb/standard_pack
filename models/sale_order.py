from odoo import models, fields, api


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    pack_compliance_status = fields.Selection(
        [
            ('compliant', 'All Standard Packs'),
            ('warning', 'Non-Standard Quantities'),
            ('pending', 'Pending Approvals'),
            ('na', 'N/A'),
        ],
        string='Pack Compliance',
        compute='_compute_pack_compliance_status',
        store=True,
    )
    has_pending_pack_requests = fields.Boolean(
        string='Pending Pack Requests',
        compute='_compute_pack_compliance_status',
        store=True,
    )

    @api.depends(
        'order_line.pack_status',
        'order_line.exception_request_id',
        'order_line.exception_request_id.state',
    )
    def _compute_pack_compliance_status(self):
        for order in self:
            lines_with_pack = order.order_line.filtered(
                lambda l: l.product_template_id.has_standard_pack and not l.display_type
            )
            if not lines_with_pack:
                order.pack_compliance_status = 'na'
                order.has_pending_pack_requests = False
                continue

            has_pending = any(
                l.exception_request_id and l.exception_request_id.state == 'pending'
                for l in lines_with_pack
            )
            has_non_compliant = any(
                l.pack_status == 'non_compliant' for l in lines_with_pack
            )

            order.has_pending_pack_requests = has_pending

            if has_pending:
                order.pack_compliance_status = 'pending'
            elif has_non_compliant:
                order.pack_compliance_status = 'warning'
            else:
                order.pack_compliance_status = 'compliant'

    def action_confirm(self):
        """Override to check pack compliance before confirming."""
        for order in self:
            pack_lines = order.order_line.filtered(
                lambda l: not l.display_type and l.product_template_id.has_standard_pack
            )
            pack_lines._check_pack_restriction()

            # Block if there are pending exception requests
            pending = pack_lines.filtered(
                lambda l: l.exception_request_id and l.exception_request_id.state == 'pending'
            )
            if pending:
                from odoo.exceptions import ValidationError
                raise ValidationError(_(
                    'Cannot confirm: there are pending exception requests '
                    'for the following products: %s',
                    ', '.join(pending.mapped('product_id.display_name')),
                ))

        return super().action_confirm()
