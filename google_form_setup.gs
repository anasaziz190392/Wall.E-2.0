/**
 * One-click setup of the RFQ intake form + response sheet in YOUR Google account.
 *
 * 1. Sign in at https://script.google.com with the Google account that should own the form.
 * 2. New project -> paste this whole file -> Save.
 * 3. Select `createRfqForm` for buyer RFQs or `createSupplierForm` for supplier profiles -> Run -> accept the permission prompts
 *    (it needs Forms + Sheets + Drive access to *your* account only).
 * 4. View -> Logs (or Execution log) prints:
 *      - FORM link to share with buyers
 *      - SHEET link to paste into the Negotiation Hub sidebar
 * 5. Open the SHEET -> Share -> "Anyone with the link: Viewer" (or use a service account, see README).
 *
 * Question titles are matched by keyword in rfq_intake.py - keep the key words if you rename them
 * (e.g. "Item 2 - description", "Item 2 - quantity", "Supplier 1 - name", "Supplier 1 - email").
 *
 * Multi-item RFQ : up to MAX_ITEMS line items (Item 1 is required, the rest are optional).
 * Supplier list  : up to MAX_SUPPLIERS suppliers with an e-mail each. The Hub uses these e-mails to send the
 *                  award / regret notifications after the buyer has approved a supplier.
 */
var MAX_ITEMS = 5;
var MAX_SUPPLIERS = 5;

function createRfqForm() {
  var form = FormApp.create('RFQ - Request for Quotation');
  form.setDescription('Submit your sourcing requirements. Fields marked (private) are used only by the buyer ' +
                      'negotiation agent and are never shown to suppliers.');
  form.setCollectEmail(false);

  form.addTextItem().setTitle('Company / requester name').setRequired(true);
  form.addTextItem().setTitle('Contact email').setRequired(true)
      .setValidation(FormApp.createTextValidation().requireTextIsEmail().build());

  var num = function (min, max) {
    return FormApp.createTextValidation().requireNumberBetween(min, max).build();
  };

  // ---- line items: one supplier quotes the whole package ----
  form.addSectionHeaderItem().setTitle('Items to quote')
      .setHelpText('List every item you need from the same supplier. Only Item 1 is mandatory.');
  for (var i = 1; i <= MAX_ITEMS; i++) {
    var req = (i === 1);
    form.addTextItem().setTitle('Item ' + i + ' - description').setRequired(req);
    form.addTextItem().setTitle('Item ' + i + ' - quantity').setRequired(req).setValidation(num(1, 1000000));
  }

  form.addSectionHeaderItem().setTitle('Commercial limits');
  form.addTextItem().setTitle('Max price - total budget ceiling in USD (private)').setRequired(true)
      .setValidation(num(1, 100000000));
  form.addTextItem().setTitle('Target delivery (days)').setRequired(true).setValidation(num(1, 365));
  form.addTextItem().setTitle('Latest acceptable delivery (days) (private)').setRequired(true)
      .setValidation(num(1, 365));
  form.addTextItem().setTitle('Preferred payment terms (Net days)').setRequired(true).setValidation(num(0, 180));
  form.addTextItem().setTitle('Shortest acceptable payment terms (Net days) (private)').setRequired(true)
      .setValidation(num(0, 180));
  form.addTextItem().setTitle('Counter-offer rounds (1-6)').setRequired(false).setValidation(num(1, 6));

  // ---- supplier contacts (for award / regret e-mails) ----
  form.addSectionHeaderItem().setTitle('Suppliers to invite')
      .setHelpText('Name and e-mail of each supplier that should take part in the negotiation. ' +
                   'They are notified of the outcome after you approve a selection. Supplier economics are collected ' +
                   'separately with createSupplierForm.');
  var mail = FormApp.createTextValidation().requireTextIsEmail().build();
  for (var j = 1; j <= MAX_SUPPLIERS; j++) {
    var needed = (j === 1);
    form.addTextItem().setTitle('Supplier ' + j + ' - name').setRequired(needed);
    form.addTextItem().setTitle('Supplier ' + j + ' - email').setRequired(needed).setValidation(mail);
  }

  var ss = SpreadsheetApp.create('RFQ Responses');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  Logger.log('FORM (share with buyers): ' + form.getPublishedUrl());
  Logger.log('FORM (edit):              ' + form.getEditUrl());
  Logger.log('SHEET (paste into app):   ' + ss.getUrl());
}

/** Create a separate supplier registration form and linked response sheet. */
function createSupplierForm() {
  var form = FormApp.create('Negotiation Hub - Supplier Registration');
  form.setDescription('Supplier profile for RFQ negotiations. Submit one response per supplier. ' +
                      'Floor price and cost assumptions are confidential buyer-agent inputs; the response sheet ' +
                      'must be kept private and is only imported into the Negotiation Hub supplier panel.');
  form.setCollectEmail(false);

  var num = function (min, max) {
    return FormApp.createTextValidation().requireNumberBetween(min, max).build();
  };
  var mail = FormApp.createTextValidation().requireTextIsEmail().build();
  form.addSectionHeaderItem().setTitle('Supplier details')
      .setHelpText('Enter profile values for the full RFQ package. Currency values are USD.');
  form.addTextItem().setTitle('Supplier name').setRequired(true);
  form.addTextItem().setTitle('Contact email').setRequired(true).setValidation(mail);
  form.addTextItem().setTitle('opening_ask (USD)').setRequired(true).setValidation(num(1, 100000000));
  form.addTextItem().setTitle('floor_price (USD, private)').setRequired(true).setValidation(num(1, 100000000));
  form.addTextItem().setTitle('standard_delivery_days').setRequired(true).setValidation(num(1, 365));
  form.addTextItem().setTitle('min_delivery_days').setRequired(true).setValidation(num(1, 365));
  form.addTextItem().setTitle('preferred_payment_days (Net days)').setRequired(true).setValidation(num(0, 180));
  form.addTextItem().setTitle('expedite_premium_pct_per_day').setRequired(true).setValidation(num(0, 1000));
  form.addTextItem().setTitle('credit_cost_pct_per_day').setRequired(true).setValidation(num(0, 1000));

  var ss = SpreadsheetApp.create('Supplier Registration Responses');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId());

  Logger.log('SUPPLIER FORM (share with suppliers): ' + form.getPublishedUrl());
  Logger.log('SUPPLIER FORM (edit):                  ' + form.getEditUrl());
  Logger.log('SUPPLIER SHEET (paste into app):       ' + ss.getUrl());
}
