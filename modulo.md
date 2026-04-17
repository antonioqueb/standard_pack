## ./__init__.py
```py
from . import models
from . import wizard
```

## ./__manifest__.py
```py
{
    'name': 'Standard Pack',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Define and enforce standard packaging quantities per product on sales orders',
    'description': """
        Standard Pack Module
        ====================
        - Define standard pack configurations per product (pallet, box, bundle, etc.)
        - Enforce pack-based selling on sale order lines
        - Three permission levels: Restricted, Standard, Unrestricted
        - Approval workflow for non-standard quantities
        - Mass assignment of standard packs to products
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://alphaqueb.com',
    'license': 'LGPL-3',
    'depends': [
        'sale',
        'product',
        'stock',
        'mail',
    ],
    'data': [
        'security/standard_pack_security.xml',
        'security/ir.model.access.csv',
        'data/pack_type_data.xml',
        'views/pack_type_views.xml',
        'views/standard_pack_views.xml',
        'views/product_views.xml',
        'views/sale_order_views.xml',
        'views/pack_exception_request_views.xml',
        'wizard/mass_assign_pack_views.xml',
        'views/menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
```

## ./data/pack_type_data.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <record id="pack_type_pallet" model="standard.pack.type">
            <field name="name">Tarima</field>
            <field name="code">PALLET</field>
            <field name="sequence">10</field>
            <field name="icon">fa-th</field>
            <field name="description">Tarima estándar de producto</field>
        </record>

        <record id="pack_type_box" model="standard.pack.type">
            <field name="name">Caja</field>
            <field name="code">BOX</field>
            <field name="sequence">20</field>
            <field name="icon">fa-cube</field>
            <field name="description">Caja de producto</field>
        </record>

        <record id="pack_type_bundle" model="standard.pack.type">
            <field name="name">Bulto</field>
            <field name="code">BUNDLE</field>
            <field name="sequence">30</field>
            <field name="icon">fa-cubes</field>
            <field name="description">Bulto/paquete de producto</field>
        </record>

        <record id="pack_type_bag" model="standard.pack.type">
            <field name="name">Saco</field>
            <field name="code">BAG</field>
            <field name="sequence">40</field>
            <field name="icon">fa-archive</field>
            <field name="description">Saco de producto</field>
        </record>

        <record id="pack_type_container" model="standard.pack.type">
            <field name="name">Contenedor</field>
            <field name="code">CONTAINER</field>
            <field name="sequence">50</field>
            <field name="icon">fa-truck</field>
            <field name="description">Contenedor completo</field>
        </record>
    </data>
</odoo>
```

## ./models/__init__.py
```py
from . import pack_type
from . import standard_pack
from . import product_template
from . import sale_order
from . import sale_order_line
from . import pack_exception_request
```

## ./models/pack_exception_request.py
```py
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

    def _notify_approvers(self):
        """Notify approvers on the exception request chatter."""
        self.ensure_one()
        approvers = self._get_approver_users()
        if not approvers:
            return

        partner_ids = approvers.mapped('partner_id').ids
        self.message_subscribe(partner_ids=partner_ids)

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
        self.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=partner_ids,
        )

        for approver in approvers:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=approver.id,
                summary=_('Excepción pack: %s — %s',
                          self.product_id.display_name,
                          self.sale_order_id.name),
                note=_('%s solicita vender %s de %s (pack estándar: %s). Motivo: %s',
                       self.requester_id.name,
                       f"{self.requested_qty:g}",
                       self.product_id.display_name,
                       self.standard_pack_id.display_name or 'N/A',
                       self.reason or ''),
            )

    def _notify_requester(self, action_type):
        """Notify the requester ONLY on the sale order chatter."""
        self.ensure_one()
        requester_partner_id = self.requester_id.partner_id.id

        self.sale_order_id.message_subscribe(partner_ids=[requester_partner_id])

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

        self.sale_order_id.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
            partner_ids=[requester_partner_id],
        )

        # Create activity on the sale order for the requester
        if action_type == 'approved':
            summary = _('Excepción aprobada — confirmar orden')
            note = _('La excepción para %s (%s uds) fue aprobada. Puedes confirmar la orden.',
                     self.product_id.display_name,
                     f"{self.requested_qty:g}")
        else:
            summary = _('Excepción rechazada — ajustar cantidad')
            note = _('La excepción para %s (%s uds) fue rechazada. Motivo: %s',
                     self.product_id.display_name,
                     f"{self.requested_qty:g}",
                     self.rejection_reason or '')

        self.sale_order_id.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.requester_id.id,
            summary=summary,
            note=note,
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
        }```

## ./models/pack_type.py
```py
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
```

## ./models/product_template.py
```py
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
```

## ./models/sale_order.py
```py
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
```

## ./models/sale_order_line.py
```py
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
            self.exception_request_id = False```

## ./models/standard_pack.py
```py
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
```

## ./security/standard_pack_security.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ============================================================ -->
    <!-- Module Category                                               -->
    <!-- ============================================================ -->
    <record id="module_category_standard_pack" model="ir.module.category">
        <field name="name">Standard Pack</field>
        <field name="description">Standard Pack access control</field>
        <field name="sequence">50</field>
    </record>

    <!-- ============================================================ -->
    <!-- Security Groups                                               -->
    <!-- ============================================================ -->

    <!-- Level 1: Restricted — can only sell in exact standard packs -->
    <!-- Must request exception for any non-standard quantity         -->
    <record id="group_standard_pack_restricted" model="res.groups">
        <field name="name">Standard Pack: Restricted Seller</field>
        <field name="category_id" ref="module_category_standard_pack"/>
        <field name="comment">
            Can only sell in exact standard pack multiples.
            Must submit an exception request to sell non-standard quantities.
            Cannot confirm orders with non-compliant lines.
        </field>
    </record>

    <!-- Level 2: Standard — can sell but gets warnings -->
    <!-- Still blocked from confirming non-compliant, needs exception -->
    <record id="group_standard_pack_standard" model="res.groups">
        <field name="name">Standard Pack: Standard Seller</field>
        <field name="category_id" ref="module_category_standard_pack"/>
        <field name="implied_ids" eval="[(4, ref('group_standard_pack_restricted'))]"/>
        <field name="comment">
            Can enter any quantity but is warned about non-standard quantities.
            Must request exception approval before confirming non-compliant orders.
        </field>
    </record>

    <!-- Level 3: Unrestricted — full access, only warnings -->
    <record id="group_standard_pack_unrestricted" model="res.groups">
        <field name="name">Standard Pack: Unrestricted Seller</field>
        <field name="category_id" ref="module_category_standard_pack"/>
        <field name="implied_ids" eval="[(4, ref('group_standard_pack_standard'))]"/>
        <field name="comment">
            Can sell any quantity without restriction.
            Still receives visual warnings for non-standard quantities.
        </field>
    </record>

    <!-- Approver — can approve/reject exception requests -->
    <record id="group_standard_pack_approver" model="res.groups">
        <field name="name">Standard Pack: Approver</field>
        <field name="category_id" ref="module_category_standard_pack"/>
        <field name="comment">
            Can approve or reject standard pack exception requests.
            Typically assigned to sales managers or production leads.
        </field>
    </record>

    <!-- Manager — can configure pack types and standard packs -->
    <record id="group_standard_pack_manager" model="res.groups">
        <field name="name">Standard Pack: Manager</field>
        <field name="category_id" ref="module_category_standard_pack"/>
        <field name="implied_ids" eval="[(4, ref('group_standard_pack_approver'))]"/>
        <field name="comment">
            Full configuration access: create/edit pack types,
            define standard packs, mass assign, and approve exceptions.
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Record Rules                                                  -->
    <!-- ============================================================ -->
    <record id="rule_exception_request_restricted" model="ir.rule">
        <field name="name">Exception Request: Restricted sees own</field>
        <field name="model_id" ref="model_pack_exception_request"/>
        <field name="groups" eval="[(4, ref('group_standard_pack_restricted'))]"/>
        <field name="domain_force">[('requester_id', '=', user.id)]</field>
        <field name="perm_read" eval="True"/>
        <field name="perm_write" eval="True"/>
        <field name="perm_create" eval="True"/>
        <field name="perm_unlink" eval="False"/>
    </record>

    <record id="rule_exception_request_approver" model="ir.rule">
        <field name="name">Exception Request: Approver sees all</field>
        <field name="model_id" ref="model_pack_exception_request"/>
        <field name="groups" eval="[(4, ref('group_standard_pack_approver'))]"/>
        <field name="domain_force">[(1, '=', 1)]</field>
    </record>
</odoo>
```

## ./views/menus.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ============================================================ -->
    <!-- Root Menu                                                     -->
    <!-- ============================================================ -->
    <menuitem id="menu_standard_pack_root"
              name="Standard Pack"
              web_icon="standard_pack,static/description/icon.png"
              sequence="45"/>

    <!-- ============================================================ -->
    <!-- Configuration                                                 -->
    <!-- ============================================================ -->
    <menuitem id="menu_standard_pack_config"
              name="Configuration"
              parent="menu_standard_pack_root"
              sequence="90"
              groups="standard_pack.group_standard_pack_manager"/>

    <!-- Pack Types -->
    <record id="action_pack_type" model="ir.actions.act_window">
        <field name="name">Pack Types</field>
        <field name="res_model">standard.pack.type</field>
        <field name="view_mode">list,form</field>
    </record>

    <menuitem id="menu_pack_type"
              name="Pack Types"
              parent="menu_standard_pack_config"
              action="action_pack_type"
              sequence="10"/>

    <!-- ============================================================ -->
    <!-- Standard Packs                                                -->
    <!-- ============================================================ -->
    <record id="action_standard_pack" model="ir.actions.act_window">
        <field name="name">Standard Packs</field>
        <field name="res_model">standard.pack</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_standard_pack_search"/>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                Define your first standard pack
            </p>
            <p>
                Standard packs define the valid packaging quantities
                for each product (e.g., Tarima x 500 pzas).
            </p>
        </field>
    </record>

    <menuitem id="menu_standard_pack"
              name="Standard Packs"
              parent="menu_standard_pack_root"
              action="action_standard_pack"
              sequence="10"/>

    <!-- ============================================================ -->
    <!-- Exception Requests                                            -->
    <!-- ============================================================ -->
    <menuitem id="menu_exception_requests"
              name="Exception Requests"
              parent="menu_standard_pack_root"
              action="action_pack_exception_request"
              sequence="20"/>

    <!-- Pending Approvals (filtered) -->
    <record id="action_pack_exception_pending" model="ir.actions.act_window">
        <field name="name">Pending Approvals</field>
        <field name="res_model">pack.exception.request</field>
        <field name="view_mode">list,form</field>
        <field name="domain">[('state', '=', 'pending')]</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                No pending approvals
            </p>
        </field>
    </record>

    <menuitem id="menu_exception_pending"
              name="Pending Approvals"
              parent="menu_standard_pack_root"
              action="action_pack_exception_pending"
              sequence="21"
              groups="standard_pack.group_standard_pack_approver"/>
</odoo>
```

## ./views/pack_exception_request_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ============================================================ -->
    <!-- Exception Request List View                                   -->
    <!-- ============================================================ -->
    <record id="view_pack_exception_request_list" model="ir.ui.view">
        <field name="name">pack.exception.request.list</field>
        <field name="model">pack.exception.request</field>
        <field name="arch" type="xml">
            <list string="Pack Exception Requests"
                  decoration-warning="state == 'pending'"
                  decoration-success="state == 'approved'"
                  decoration-danger="state == 'rejected'">
                <field name="create_date" string="Date"/>
                <field name="sale_order_id"/>
                <field name="partner_id"/>
                <field name="product_id"/>
                <field name="pack_type_name"/>
                <field name="qty_per_pack" string="Std Qty/Pack"/>
                <field name="requested_qty"/>
                <field name="pack_compliant_qty" string="Nearest Std"/>
                <field name="difference"/>
                <field name="requester_id"/>
                <field name="approver_id" optional="show"/>
                <field name="state" widget="badge"
                       decoration-warning="state == 'pending'"
                       decoration-success="state == 'approved'"
                       decoration-danger="state == 'rejected'"/>
            </list>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Exception Request Form View                                   -->
    <!-- ============================================================ -->
    <record id="view_pack_exception_request_form" model="ir.ui.view">
        <field name="name">pack.exception.request.form</field>
        <field name="model">pack.exception.request</field>
        <field name="arch" type="xml">
            <form string="Pack Exception Request">
                <header>
                    <button name="action_approve" string="Approve"
                            type="object" class="btn-primary"
                            invisible="state != 'pending'"
                            groups="standard_pack.group_standard_pack_approver"/>
                    <button name="action_reject" string="Reject"
                            type="object" class="btn-danger"
                            invisible="state != 'pending'"
                            groups="standard_pack.group_standard_pack_approver"/>
                    <button name="action_reset_to_pending" string="Reset to Pending"
                            type="object" class="btn-secondary"
                            invisible="state == 'pending'"
                            groups="standard_pack.group_standard_pack_manager"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="pending,approved,rejected"/>
                </header>
                <sheet>
                    <div class="oe_title">
                        <h1>
                            <field name="display_name" readonly="1"/>
                        </h1>
                    </div>
                    <group>
                        <group string="Request Details">
                            <field name="sale_order_id"/>
                            <field name="sale_line_id"/>
                            <field name="product_id"/>
                            <field name="partner_id"/>
                        </group>
                        <group string="Pack Information">
                            <field name="standard_pack_id"/>
                            <field name="pack_type_name"/>
                            <field name="qty_per_pack"/>
                        </group>
                    </group>
                    <group>
                        <group string="Quantities">
                            <field name="requested_qty"/>
                            <field name="pack_compliant_qty"/>
                            <field name="difference"/>
                        </group>
                        <group string="Approval">
                            <field name="requester_id"/>
                            <field name="approver_id"/>
                        </group>
                    </group>
                    <group>
                        <field name="reason" placeholder="Explain why a non-standard quantity is needed..."/>
                        <field name="rejection_reason"
                               invisible="state != 'rejected'"
                               readonly="1"/>
                    </group>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Search View                                                   -->
    <!-- ============================================================ -->
    <record id="view_pack_exception_request_search" model="ir.ui.view">
        <field name="name">pack.exception.request.search</field>
        <field name="model">pack.exception.request</field>
        <field name="arch" type="xml">
            <search string="Exception Requests">
                <field name="sale_order_id"/>
                <field name="product_id"/>
                <field name="partner_id"/>
                <field name="requester_id"/>
                <filter name="filter_pending" string="Pending"
                        domain="[('state', '=', 'pending')]"/>
                <filter name="filter_approved" string="Approved"
                        domain="[('state', '=', 'approved')]"/>
                <filter name="filter_rejected" string="Rejected"
                        domain="[('state', '=', 'rejected')]"/>
                <separator/>
                <filter name="filter_my_requests" string="My Requests"
                        domain="[('requester_id', '=', uid)]"/>
                <separator/>
                <group expand="0" string="Group By">
                    <filter name="group_state" string="Status"
                            context="{'group_by': 'state'}"/>
                    <filter name="group_product" string="Product"
                            context="{'group_by': 'product_id'}"/>
                    <filter name="group_requester" string="Requester"
                            context="{'group_by': 'requester_id'}"/>
                    <filter name="group_partner" string="Customer"
                            context="{'group_by': 'partner_id'}"/>
                </group>
            </search>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Action                                                        -->
    <!-- ============================================================ -->
    <record id="action_pack_exception_request" model="ir.actions.act_window">
        <field name="name">Exception Requests</field>
        <field name="res_model">pack.exception.request</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_pack_exception_request_search"/>
        <field name="context">{'search_default_filter_pending': 1}</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">
                No exception requests yet
            </p>
            <p>
                Exception requests are created when a seller needs to sell
                a non-standard pack quantity.
            </p>
        </field>
    </record>
</odoo>
```

## ./views/pack_type_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- List View -->
    <record id="view_pack_type_list" model="ir.ui.view">
        <field name="name">standard.pack.type.list</field>
        <field name="model">standard.pack.type</field>
        <field name="arch" type="xml">
            <list string="Pack Types" editable="bottom">
                <field name="sequence" widget="handle"/>
                <field name="icon"/>
                <field name="name"/>
                <field name="code"/>
                <field name="description" optional="show"/>
                <field name="active" column_invisible="True"/>
            </list>
        </field>
    </record>

    <!-- Form View -->
    <record id="view_pack_type_form" model="ir.ui.view">
        <field name="name">standard.pack.type.form</field>
        <field name="model">standard.pack.type</field>
        <field name="arch" type="xml">
            <form string="Pack Type">
                <sheet>
                    <div class="oe_title">
                        <h1>
                            <field name="name" placeholder="e.g., Tarima"/>
                        </h1>
                    </div>
                    <group>
                        <group>
                            <field name="code"/>
                            <field name="icon"/>
                            <field name="sequence"/>
                        </group>
                        <group>
                            <field name="active"/>
                        </group>
                    </group>
                    <field name="description" placeholder="Description..."/>
                </sheet>
            </form>
        </field>
    </record>
</odoo>
```

## ./views/product_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Inherit product.template form: add Standard Packs tab -->
    <record id="view_product_template_form_standard_pack" model="ir.ui.view">
        <field name="name">product.template.form.standard.pack</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product.product_template_only_form_view"/>
        <field name="arch" type="xml">
            <xpath expr="//page[@name='inventory']" position="after">
                <page string="Standard Pack" name="standard_pack">
                    <group>
                        <group>
                            <field name="has_standard_pack" readonly="1"/>
                            <field name="default_pack_id" readonly="1"/>
                        </group>
                        <group>
                            <field name="standard_pack_count" string="Packs Defined"/>
                        </group>
                    </group>
                    <field name="standard_pack_ids">
                        <list editable="bottom">
                            <field name="sequence" widget="handle"/>
                            <field name="pack_type_id"/>
                            <field name="qty_per_pack"/>
                            <field name="uom_id" readonly="1"/>
                            <field name="is_default"/>
                        </list>
                    </field>
                </page>
            </xpath>
        </field>
    </record>

    <!-- Product list: add standard pack indicator -->
    <record id="view_product_template_list_standard_pack" model="ir.ui.view">
        <field name="name">product.template.list.standard.pack</field>
        <field name="model">product.template</field>
        <field name="inherit_id" ref="product.product_template_tree_view"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='type']" position="after">
                <field name="has_standard_pack" string="Std Pack"
                       widget="boolean_toggle" optional="show"/>
            </xpath>
        </field>
    </record>
</odoo>
```

## ./views/sale_order_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_sale_order_form_pack" model="ir.ui.view">
        <field name="name">sale.order.form.standard.pack</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='payment_term_id']" position="after">
                <field name="pack_compliance_status" widget="badge"
                       decoration-success="pack_compliance_status == 'compliant'"
                       decoration-warning="pack_compliance_status == 'warning'"
                       decoration-danger="pack_compliance_status == 'pending'"
                       decoration-info="pack_compliance_status == 'na'"
                       readonly="1"/>
            </xpath>

            <xpath expr="//field[@name='order_line']/list/field[@name='product_uom_qty']" position="before">
                <field name="has_standard_pack" column_invisible="True"/>
                <field name="standard_pack_id"
                       optional="show"
                       options="{'no_create': True, 'no_open': True}"/>
                <field name="pack_qty" optional="show" string="# Packs"/>
                <field name="qty_per_pack" optional="hide"/>
            </xpath>

            <xpath expr="//field[@name='order_line']/list/field[@name='product_uom_qty']" position="after">
                <field name="pack_status" widget="badge"
                       decoration-success="pack_status == 'compliant'"
                       decoration-warning="pack_status == 'non_compliant'"
                       decoration-info="pack_status == 'approved_exception'"
                       decoration-danger="pack_status in ('pending_exception', 'rejected_exception')"
                       optional="show"/>
                <field name="pack_status_message" optional="hide"/>
                <button name="action_request_pack_exception"
                        string="Request"
                        type="object"
                        class="btn-link text-warning"
                        invisible="pack_status not in ('non_compliant', 'rejected_exception')"
                        icon="fa-exclamation-triangle"/>
            </xpath>

            <xpath expr="//field[@name='order_line']/form//field[@name='product_uom_qty']" position="after">
                <field name="has_standard_pack" invisible="True"/>
                <field name="standard_pack_id" options="{'no_create': True}"/>
                <field name="pack_qty" string="# Packs"/>
                <field name="pack_status" widget="badge"
                       decoration-success="pack_status == 'compliant'"
                       decoration-warning="pack_status == 'non_compliant'"
                       decoration-info="pack_status == 'approved_exception'"
                       decoration-danger="pack_status in ('pending_exception', 'rejected_exception')"
                       readonly="1"/>
                <field name="pack_status_message" readonly="1"/>
                <field name="exception_request_id" readonly="1"
                       invisible="not exception_request_id"/>
                <button name="action_request_pack_exception"
                        string="Request Exception"
                        type="object" class="btn-link"
                        invisible="pack_status not in ('non_compliant', 'rejected_exception')"
                        icon="fa-exclamation-triangle"/>
                <button name="action_reset_exception"
                        string="New Request"
                        type="object" class="btn-link text-danger"
                        invisible="pack_status != 'rejected_exception'"
                        icon="fa-refresh"/>
            </xpath>
        </field>
    </record>

    <record id="view_sale_order_list_pack" model="ir.ui.view">
        <field name="name">sale.order.list.standard.pack</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_tree"/>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='state']" position="before">
                <field name="pack_compliance_status" widget="badge"
                       decoration-success="pack_compliance_status == 'compliant'"
                       decoration-warning="pack_compliance_status == 'warning'"
                       decoration-danger="pack_compliance_status == 'pending'"
                       optional="show" string="Pack"/>
            </xpath>
        </field>
    </record>
</odoo>```

## ./views/standard_pack_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- List View -->
    <record id="view_standard_pack_list" model="ir.ui.view">
        <field name="name">standard.pack.list</field>
        <field name="model">standard.pack</field>
        <field name="arch" type="xml">
            <list string="Standard Packs" editable="bottom" multi_edit="1">
                <field name="sequence" widget="handle"/>
                <field name="product_tmpl_id"/>
                <field name="pack_type_id"/>
                <field name="qty_per_pack"/>
                <field name="uom_id" readonly="1"/>
                <field name="is_default"/>
                <field name="company_id" column_invisible="True"/>
            </list>
        </field>
    </record>

    <!-- Form View -->
    <record id="view_standard_pack_form" model="ir.ui.view">
        <field name="name">standard.pack.form</field>
        <field name="model">standard.pack</field>
        <field name="arch" type="xml">
            <form string="Standard Pack">
                <sheet>
                    <div class="oe_title">
                        <h1>
                            <field name="display_name" readonly="1"/>
                        </h1>
                    </div>
                    <group>
                        <group>
                            <field name="product_tmpl_id"/>
                            <field name="pack_type_id"/>
                        </group>
                        <group>
                            <field name="qty_per_pack"/>
                            <field name="uom_id"/>
                            <field name="is_default"/>
                        </group>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <!-- Search View -->
    <record id="view_standard_pack_search" model="ir.ui.view">
        <field name="name">standard.pack.search</field>
        <field name="model">standard.pack</field>
        <field name="arch" type="xml">
            <search string="Standard Packs">
                <field name="product_tmpl_id"/>
                <field name="pack_type_id"/>
                <filter name="filter_default" string="Default Packs" domain="[('is_default', '=', True)]"/>
                <separator/>
                <group expand="0" string="Group By">
                    <filter name="group_product" string="Product" context="{'group_by': 'product_tmpl_id'}"/>
                    <filter name="group_type" string="Pack Type" context="{'group_by': 'pack_type_id'}"/>
                </group>
            </search>
        </field>
    </record>
</odoo>
```

## ./wizard/__init__.py
```py
from . import mass_assign_pack
```

## ./wizard/mass_assign_pack.py
```py
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
        return {'type': 'ir.actions.act_window_close'}```

## ./wizard/mass_assign_pack_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- ============================================================ -->
    <!-- Exception Request Wizard (from sale order line)                -->
    <!-- ============================================================ -->
    <record id="view_pack_exception_request_wizard_form" model="ir.ui.view">
        <field name="name">pack.exception.request.wizard.form</field>
        <field name="model">pack.exception.request.wizard</field>
        <field name="arch" type="xml">
            <form string="Request Pack Exception">
                <group string="This quantity does not match the standard pack">
                    <group>
                        <field name="sale_order_id" readonly="1"/>
                        <field name="product_id" readonly="1"/>
                        <field name="standard_pack_id" readonly="1"/>
                    </group>
                    <group>
                        <field name="requested_qty" readonly="1"/>
                        <field name="pack_compliant_qty" readonly="1"/>
                    </group>
                </group>
                <group>
                    <field name="reason" placeholder="Explain why you need a non-standard quantity..."
                           widget="text"/>
                </group>
                <field name="sale_line_id" invisible="1"/>
                <footer>
                    <button name="action_submit_request" string="Submit Request"
                            type="object" class="btn-primary"
                            icon="fa-paper-plane"/>
                    <button string="Cancel" class="btn-secondary"
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Mass Assign Pack Wizard                                       -->
    <!-- ============================================================ -->
    <record id="view_mass_assign_pack_wizard_form" model="ir.ui.view">
        <field name="name">mass.assign.pack.wizard.form</field>
        <field name="model">mass.assign.pack.wizard</field>
        <field name="arch" type="xml">
            <form string="Mass Assign Standard Pack">
                <group>
                    <group>
                        <field name="pack_type_id"/>
                        <field name="qty_per_pack"/>
                        <field name="is_default"/>
                    </group>
                    <group>
                        <field name="overwrite_existing"/>
                        <field name="preview_count" readonly="1"
                               string="Products affected"/>
                    </group>
                </group>
                <group string="Specific Products (leave empty to use selected)">
                    <field name="product_tmpl_ids" nolabel="1"
                           widget="many2many_tags"/>
                </group>
                <footer>
                    <button name="action_assign" string="Assign Pack"
                            type="object" class="btn-primary"/>
                    <button string="Cancel" class="btn-secondary"
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>

    <!-- Action for wizard (from product list) -->
    <record id="action_mass_assign_pack_wizard" model="ir.actions.act_window">
        <field name="name">Assign Standard Pack</field>
        <field name="res_model">mass.assign.pack.wizard</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
        <field name="binding_model_id" ref="product.model_product_template"/>
        <field name="binding_view_types">list</field>
    </record>

    <!-- ============================================================ -->
    <!-- Reject Wizard                                                 -->
    <!-- ============================================================ -->
    <record id="view_pack_exception_reject_wizard_form" model="ir.ui.view">
        <field name="name">pack.exception.reject.wizard.form</field>
        <field name="model">pack.exception.reject.wizard</field>
        <field name="arch" type="xml">
            <form string="Reject Exception Request">
                <group>
                    <field name="request_id" readonly="1"/>
                    <field name="rejection_reason"
                           placeholder="Explain why this exception is rejected..."
                           widget="text"/>
                </group>
                <footer>
                    <button name="action_confirm_reject" string="Confirm Rejection"
                            type="object" class="btn-danger"/>
                    <button string="Cancel" class="btn-secondary"
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>
</odoo>```

