# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import UserError


class MailTemplatePreview(models.TransientModel):
    _name = 'mail.template.preview'
    _description = 'Email Template Preview'
    _MAIL_TEMPLATE_FIELDS = ['subject', 'body_html', 'email_from', 'email_to',
                             'email_cc', 'reply_to', 'scheduled_date', 'attachment_ids']

    @api.model
    def _selection_target_model(self):
        return [(model.model, model.name) for model in self.env['ir.model'].sudo().search([])]

    @api.model
    def _selection_languages(self):
        return self.env['res.lang'].get_installed()

    @api.model
    def default_get(self, fields):
        result = super(MailTemplatePreview, self).default_get(fields)
        if not result.get('mail_template_id') or 'resource_ref' not in fields:
            return result
        mail_template = self.env['mail.template'].browse(result['mail_template_id']).sudo()
        model = mail_template.model
        res = self.env[model].search([], limit=1)
        if res:
            result['resource_ref'] = '%s,%s' % (model, res.id)
        return result

    mail_template_id = fields.Many2one('mail.template', string='Related Mail Template', required=True)
    model_id = fields.Many2one('ir.model', string='Targeted model', related="mail_template_id.model_id")
    resource_ref = fields.Reference(string='Record', selection='_selection_target_model')
    lang = fields.Selection(_selection_languages, string='Template Preview Language')
    no_record = fields.Boolean('No Record', compute='_compute_no_record')
    error_msg = fields.Char('Error Message', readonly=True)
    # Fields same than the mail.template model, computed with resource_ref and lang
    subject = fields.Char('Subject', compute='_compute_mail_template_fields')
    email_from = fields.Char('From', compute='_compute_mail_template_fields', help="Sender address")
    email_to = fields.Char('To', compute='_compute_mail_template_fields',
                           help="Comma-separated recipient addresses")
    email_cc = fields.Char('Cc', compute='_compute_mail_template_fields', help="Carbon copy recipients")
    reply_to = fields.Char('Reply-To', compute='_compute_mail_template_fields', help="Preferred response address")
    scheduled_date = fields.Char('Scheduled Date', compute='_compute_mail_template_fields',
                                 help="The queue manager will send the email after the date")
    body_html = fields.Html('Body', compute='_compute_mail_template_fields', sanitize=False)
    attachment_ids = fields.Many2many('ir.attachment', 'Attachments', compute='_compute_mail_template_fields')
    # Extra fields info generated by generate_email
    partner_ids = fields.Many2many('res.partner', string='Recipients', compute='_compute_mail_template_fields')

    @api.depends('model_id')
    def _compute_no_record(self):
        for preview, preview_sudo in zip(self, self.sudo()):
            model_id = preview_sudo.model_id
            preview.no_record = not model_id or not self.env[model_id.model].search_count([])

    @api.depends('lang', 'resource_ref')
    def _compute_mail_template_fields(self):
        """ Preview the mail template (body, subject, ...) depending of the language and
        the record reference, more precisely the record id for the defined model of the mail template.
        If no record id is selectable/set, the inline_template placeholders won't be replace in the display information. """
        copy_depends_values = {'lang': self.lang}
        mail_template = self.mail_template_id.with_context(lang=self.lang)
        try:
            if not self.resource_ref:
                self._set_mail_attributes()
            else:
                copy_depends_values['resource_ref'] = '%s,%s' % (self.resource_ref._name, self.resource_ref.id)
                mail_values = mail_template.with_context(template_preview_lang=self.lang).generate_email(
                    self.resource_ref.id, self._MAIL_TEMPLATE_FIELDS + ['partner_to'])
                self._set_mail_attributes(values=mail_values)
            self.error_msg = False
        except UserError as user_error:
            self._set_mail_attributes()
            self.error_msg = user_error.args[0]
        finally:
            # Avoid to be change by a invalidate_cache call (in generate_mail), e.g. Quotation / Order report
            for key, value in copy_depends_values.items():
                self[key] = value

    def _set_mail_attributes(self, values=None):
        for field in self._MAIL_TEMPLATE_FIELDS:
            field_value = values.get(field, False) if values else self.mail_template_id[field]
            self[field] = field_value
        self.partner_ids = values.get('partner_ids', False) if values else False
