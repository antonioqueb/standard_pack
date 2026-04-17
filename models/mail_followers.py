import logging
from odoo import models

_logger = logging.getLogger(__name__)


class MailFollowers(models.Model):
    _inherit = 'mail.followers'

    def _insert_followers(self, res_model, res_ids, partner_ids,
                          subtypes=None, customer_ids=None,
                          check_existing=True, existing_policy='skip'):
        """Force skip policy to avoid UniqueViolation on mail_followers."""
        if existing_policy != 'skip':
            _logger.info(
                "[standard_pack] Forzando existing_policy='skip' "
                "(venía %s) para %s ids=%s partners=%s",
                existing_policy, res_model, res_ids, partner_ids,
            )
        return super()._insert_followers(
            res_model, res_ids, partner_ids,
            subtypes=subtypes,
            customer_ids=customer_ids,
            check_existing=True,
            existing_policy='skip',
        )