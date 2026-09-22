import frappe

from pranera_crm.settings import ensure_default


def after_install():
	ensure_default()
	ensure_payment_terms_template()


def after_migrate():
	ensure_default()
	ensure_payment_terms_template()


def ensure_payment_terms_template():
	"""The seeded "payment_terms" Customer Wizard Mapping question points at this
	template; the site ships with none, so create it once (never touched again)."""
	name = "100% Advance"
	if frappe.db.exists("Payment Terms Template", name):
		return
	frappe.get_doc(
		{
			"doctype": "Payment Terms Template",
			"template_name": name,
			"terms": [
				{
					"invoice_portion": 100,
					"due_date_based_on": "Day(s) after invoice date",
					"credit_days": 0,
					"description": "100% payable in advance",
				}
			],
		}
	).insert(ignore_permissions=True)
