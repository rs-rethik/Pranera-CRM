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

		# 302, not the 301 default: a browser may cache a permanent redirect and
		# keep sending the user to /login even after they have signed in. Set on
		# the instance since v15's Redirect takes no constructor argument.
		redirect = frappe.Redirect()
		redirect.http_status_code = 302
		raise redirect

	from crm.api import check_app_permission

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access Frappe CRM"), frappe.PermissionError)

	# get_csrf_token() may create the token for this session; persist it
	frappe.db.commit()
	context.boot = get_boot()
	return context


def get_boot():
	# Every key becomes a `window.<key>` global in the browser (see the frappe-ui
	# jinjaBootData vite plugin), so keep them app-specific.
	return frappe._dict(
		{
			"csrf_token": frappe.sessions.get_csrf_token(),
			"site_name": frappe.local.site,
			"pranera_user": frappe.session.user,
			"pranera_user_fullname": frappe.utils.get_fullname(frappe.session.user),
		}
	)


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	"""Boot data for `yarn dev`, where there is no Jinja to inject it."""
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()
