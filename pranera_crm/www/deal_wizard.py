"""Boot data for the /deal_wizard single page app (mirrors crm/www/crm.py)."""

from urllib.parse import quote, unquote

import frappe
from frappe import _
from frappe.translate import get_messages_for_boot

from pranera_crm.settings import get_site_properties, is_wizard_enabled

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		# Send guests to login and bring them straight back to the wizard.
		request = frappe.local.request
		target = request.path + (f"?{request.query_string.decode()}" if request.query_string else "")
		redirect_to(f"/login?redirect-to={quote(target, safe='')}")

	from crm.api import check_app_permission

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access Frappe CRM"), frappe.PermissionError)

	if not is_wizard_enabled():
		# "Enable Convert to Deal Wizard" is off in CRM Settings: use CRM's own flow
		redirect_to(crm_url_for_request())

	# get_csrf_token() may create the token for this session; persist it
	frappe.db.commit()
	context.boot = get_boot()
	return context


def crm_url_for_request() -> str:
	"""/deal_wizard/<lead> -> the same lead in CRM; anything else -> the CRM home."""
	parts = [p for p in frappe.local.request.path.split("/") if p]
	if len(parts) >= 2 and parts[0] == "deal_wizard":
		return f"/crm/leads/{quote(unquote(parts[1]), safe='')}"
	return "/crm"


def redirect_to(location: str):
	frappe.local.flags.redirect_location = location

	# 302, not the 301 default: a browser may cache a permanent redirect and keep
	# sending the user there long after the reason (signed out, wizard off) is gone.
	# Set on the instance since v15's Redirect takes no constructor argument.
	redirect = frappe.Redirect()
	redirect.http_status_code = 302
	raise redirect


def get_boot():
	# Every key becomes a `window.<key>` global in the browser (see the frappe-ui
	# jinjaBootData vite plugin), so keep them app-specific.
	return frappe._dict(
		{
			"csrf_token": frappe.sessions.get_csrf_token(),
			"site_name": frappe.local.site,
			"pranera_user": frappe.session.user,
			"pranera_user_fullname": frappe.utils.get_fullname(frappe.session.user),
			"pranera_site": get_site_properties(),
			# same as CRM: the language the site/user is set to
			"translated_messages": get_messages_for_boot(),
		}
	)


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	"""Boot data for `yarn dev`, where there is no Jinja to inject it."""
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()
