from odoo import models, fields, api, _

class account_payment(models.Model):
    _inherit = "account.payment"
    
    tax_id = fields.Many2one('account.tax', string='Tax Type')
    
    tax_amount = fields.Char('Tax Amount',compute="tax_calculate")
    
    tax_type = fields.Char('Tax categ',compute="get_tax_type")
    
    
    @api.depends('journal_id')
    def get_tax_type(self):
        if self.partner_type =='customer':
            self.tax_type ='sale'
        if self.partner_type =='supplier':
            self.tax_type ='purchase'
        if self.partner_type ==False:
            self.tax_type ='none'
    @api.depends('tax_id')
    def tax_calculate(self):
        if self.tax_id:
            self.tax_amount = ((self.amount*self.tax_id.amount)/100)
           
    def _create_payment_entry(self, amount):
        """ Create a journal entry corresponding to a payment, if the payment references invoice(s) they are reconciled.
            Return the journal entry.
        """
        aml_obj = self.env['account.move.line'].with_context(check_move_validity=False)
        invoice_currency = False
        if self.invoice_ids and all([x.currency_id == self.invoice_ids[0].currency_id for x in self.invoice_ids]):
            #if all the invoices selected share the same currency, record the paiement in that currency too
            invoice_currency = self.invoice_ids[0].currency_id
        debit, credit, amount_currency, currency_id = aml_obj.with_context(date=self.payment_date).compute_amount_fields(amount, self.currency_id, self.company_id.currency_id, invoice_currency)

        move = self.env['account.move'].create(self._get_move_vals())

        #custom method written for tax entry
        if self.tax_id:
            if self.payment_type =='inbound':
                tax =  round(((credit*self.tax_id.amount)/100))
#                 tax =  (((credit*self.tax_id.amount)/100))
                tax_aml_dict = self._get_shared_move_line_vals(tax, debit, amount_currency, move.id, False)
                tax_aml_dict.update(self._get_tax_move_line_vals(self.invoice_ids))
                tax_aml_dict.update({'currency_id': currency_id})
                tax_aml = aml_obj.create(tax_aml_dict)
                
                      
#                 payable = credit - tax
                counterpart_aml_dict = self._get_shared_move_line_vals(debit, credit, amount_currency, move.id, False)
                counterpart_aml_dict.update(self._get_counterpart_move_line_vals(self.invoice_ids))
                counterpart_aml_dict.update({'currency_id': currency_id})
                counterpart_aml = aml_obj.create(counterpart_aml_dict)
            
            if self.payment_type =='outbound':
                tax =  ((debit*self.tax_id.amount)/100)
                tax_aml_dict = self._get_shared_move_line_vals(credit, tax, amount_currency, move.id, False)
                tax_aml_dict.update(self._get_tax_move_line_vals(self.invoice_ids))
                tax_aml_dict.update({'currency_id': currency_id})
                tax_aml = aml_obj.create(tax_aml_dict)
                
                         
#                 receveable = debit - tax
                counterpart_aml_dict = self._get_shared_move_line_vals(debit, credit, amount_currency, move.id, False)
                counterpart_aml_dict.update(self._get_counterpart_move_line_vals(self.invoice_ids))
                counterpart_aml_dict.update({'currency_id': currency_id})
                counterpart_aml = aml_obj.create(counterpart_aml_dict)
            
            if self.payment_type =='transfer':
                tax =  0
        #Write line corresponding to invoice payment odoo method
        else:
            counterpart_aml_dict = self._get_shared_move_line_vals(debit, credit, amount_currency, move.id, False)
            counterpart_aml_dict.update(self._get_counterpart_move_line_vals(self.invoice_ids))
            counterpart_aml_dict.update({'currency_id': currency_id})
            counterpart_aml = aml_obj.create(counterpart_aml_dict)
            if self.payment_type =='transfer':
                tax =  0

        #Reconcile with the invoices
        if self.payment_difference_handling == 'reconcile' and self.payment_difference:
            writeoff_line = self._get_shared_move_line_vals(0, 0, 0, move.id, False)
            amount_currency_wo, currency_id = aml_obj.with_context(date=self.payment_date).compute_amount_fields(self.payment_difference, self.currency_id, self.company_id.currency_id, invoice_currency)[2:]
            # the writeoff debit and credit must be computed from the invoice residual in company currency
            # minus the payment amount in company currency, and not from the payment difference in the payment currency
            # to avoid loss of precision during the currency rate computations. See revision 20935462a0cabeb45480ce70114ff2f4e91eaf79 for a detailed example.
            total_residual_company_signed = sum(invoice.residual_company_signed for invoice in self.invoice_ids)
            total_payment_company_signed = self.currency_id.with_context(date=self.payment_date).compute(self.amount, self.company_id.currency_id)
            if self.invoice_ids[0].type in ['in_invoice', 'out_refund']:
                amount_wo = total_payment_company_signed - total_residual_company_signed
            else:
                amount_wo = total_residual_company_signed - total_payment_company_signed
            # Align the sign of the secondary currency writeoff amount with the sign of the writeoff
            # amount in the company currency
            if amount_wo > 0:
                debit_wo = amount_wo
                credit_wo = 0.0
                amount_currency_wo = abs(amount_currency_wo)
            else:
                debit_wo = 0.0
                credit_wo = -amount_wo
                amount_currency_wo = -abs(amount_currency_wo)
            writeoff_line['name'] = _('Counterpart')
            writeoff_line['account_id'] = self.writeoff_account_id.id
            writeoff_line['debit'] = debit_wo
            writeoff_line['credit'] = credit_wo
            writeoff_line['amount_currency'] = amount_currency_wo
            writeoff_line['currency_id'] = currency_id
            writeoff_line = aml_obj.create(writeoff_line)
            if counterpart_aml['debit']:
                counterpart_aml['debit'] += credit_wo - debit_wo
            if counterpart_aml['credit']:
                counterpart_aml['credit'] += debit_wo - credit_wo
            counterpart_aml['amount_currency'] -= amount_currency_wo
#         self.invoice_ids.register_payment(counterpart_aml)

        #Write counterpart lines
        if not self.currency_id != self.company_id.currency_id:
            amount_currency = 0
            

        #custom code
        flag= 0
        if credit != 0:
            bank_credit = credit - tax
            liquidity_aml_dict = self._get_shared_move_line_vals(bank_credit, debit, -amount_currency, move.id, False)
            flag =1
        if debit!=0:
            bank_debit =  debit - tax
            liquidity_aml_dict = self._get_shared_move_line_vals(credit, bank_debit, -amount_currency, move.id, False)
            flag =1
            #end
        if flag ==0:
            liquidity_aml_dict = self._get_shared_move_line_vals(credit, debit, -amount_currency, move.id, False)
        liquidity_aml_dict.update(self._get_liquidity_move_line_vals(-amount))
        aml_obj.create(liquidity_aml_dict)

        move.post()
        self.invoice_ids.register_payment(counterpart_aml)
        return move
    
    
#     def _get_shared_move_line_vals(self, debit, credit, amount_currency, move_id, invoice_id=False):
#         """ Returns values common to both move lines (except for debit, credit and amount_currency which are reversed)
#         """
#         return {
#             'partner_id': self.payment_type in ('inbound', 'outbound') and self.env['res.partner']._find_accounting_partner(self.partner_id).id or False,
#             'invoice_id': invoice_id and invoice_id.id or False,
#             'move_id': move_id,
#             'debit': debit,
#             'credit': credit,
#             'amount_currency': amount_currency or False,
#         }
    def _get_tax_move_line_vals(self, invoice=False):
        if self.payment_type == 'transfer':
            name = self.name
        else:
            name = ''
            if self.partner_type == 'customer':
                if self.payment_type == 'inbound':
                    name += _("Customer Payment")
                elif self.payment_type == 'outbound':
                    name += _("Customer Refund")
            elif self.partner_type == 'supplier':
                if self.payment_type == 'inbound':
                    name += _("Vendor Refund")
                elif self.payment_type == 'outbound':
                    name += _("Vendor Payment")
            if invoice:
                name += ': '
                for inv in invoice:
                    if inv.move_id:
                        name += inv.number + ', '
                name = name[:len(name)-2] 
        return {
            'name': name,
            'account_id': self.tax_id.account_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id != self.company_id.currency_id and self.currency_id.id or False,
            'payment_id': self.id,
        }
        
class AccountTax(models.Model):
    _inherit = 'account.tax'
    
    is_withholding_tax = fields.Boolean('Is withholding', default=False)