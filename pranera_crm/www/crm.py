"""Overrides CRM's /crm page (this app is installed after crm, so Frappe picks
this template first) only to add the Reports items to CRM's sidebar.

Everything else - permission checks, boot data, the page itself - is CRM's own:
crm.html includes crm/www/crm.html unchanged. Nothing in the crm app is modified.
"""

from crm.www import crm
from frappe.utils import get_build_version

no_cache = 1


def get_context():
	context = crm.get_context()
	# cache-buster for crm_sidebar_ext.js; not a boot key, so it never reaches window.*
	context.pranera_build_version = get_build_version()
	return context
