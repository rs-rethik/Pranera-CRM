"""Boot data for the /deal_wizard single page app (mirrors crm/www/crm.py)."""

from urllib.parse import quote

import frappe
from frappe import _

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		# Send guests to login and bring them straight back to the wizard.
		request = frappe.local.request
		target = request.path + (f"?{request.query_string.decode()}" if request.query_string else "")
		frappe.local.flags.redirect_location = f"/login?redirect-to={quote(target, safe='')}"
		raise frappe.Redirect

	from crm.api import check_app_permission

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access Frappe CRM"), frappe.PermissionError)

	frappe.db.commit()  # noqa: a csrf token may have just been generated for the session
	context.boot = frappe._dict(
		{
			"csrf_token": frappe.sessions.get_csrf_token(),
			"site_name": frappe.local.site,
			"pranera_user": frappe.session.user,
			"pranera_user_fullname": frappe.utils.get_fullname(frappe.session.user),
			"crm_url": "/crm",
		}
	)
	return context
