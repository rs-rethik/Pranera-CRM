import frappe
from frappe.utils import quote

no_cache = 1

ROUTES = {"CRM Lead": "leads", "CRM Deal": "deals"}


def get_context(context):
	name = frappe.form_dict.get("name") or ""
	if frappe.session.user == "Guest":
		location = f"/login?redirect-to={quote(f'/crm-open/{name}')}"
	else:
		location = next(
			(
				f"/crm/{route}/{name}"
				for doctype, route in ROUTES.items()
				if name and frappe.db.exists(doctype, name)
			),
			"/crm",
		)
	frappe.local.flags.redirect_location = location
	raise frappe.Redirect
