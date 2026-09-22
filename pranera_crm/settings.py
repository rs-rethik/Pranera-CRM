"""CRM Settings integration: the on/off switch and the site properties the wizard follows."""

import frappe
from frappe.utils import cint

SETTINGS = "FCRM Settings"
# Custom Field on FCRM Settings (shipped as a fixture, see fixtures/custom_field.json)
ENABLE_FIELD = "enable_convert_to_deal_wizard"


def is_wizard_enabled() -> bool:
	"""Is "Enable Convert to Deal Wizard" ticked in CRM Settings?

	Reads the raw Singles row instead of ``get_single_value``: that helper returns
	``0`` both for "unticked" and for "never saved", and a never-saved switch must
	count as enabled (its default). If the custom field doesn't exist, the wizard
	is enabled too, so a half-installed app never hides CRM's own button.
	"""
	if not frappe.get_meta(SETTINGS).has_field(ENABLE_FIELD):
		return True

	value = frappe.db.sql(
		"select `value` from `tabSingles` where `doctype` = %s and `field` = %s",
		(SETTINGS, ENABLE_FIELD),
	)
	return True if not value else bool(cint(value[0][0]))


# Set once the default has been written, so an admin's later choice is never overwritten
DEFAULT_APPLIED = "pranera_crm_wizard_default_applied"


def ensure_default():
	"""Make "Enable Convert to Deal Wizard" start out ticked, exactly once.

	Frappe stores an untouched Check on a Single as ``0`` as soon as the settings
	are saved for any reason (e.g. during migrate), which is indistinguishable
	from an admin unticking it. So the default is written the first time this
	runs, and a marker records that; from then on the stored value is the
	admin's and is never touched again.
	"""
	if not frappe.get_meta(SETTINGS).has_field(ENABLE_FIELD):
		return
	if frappe.db.get_default(DEFAULT_APPLIED):
		return

	frappe.db.set_single_value(SETTINGS, ENABLE_FIELD, 1)
	frappe.db.set_default(DEFAULT_APPLIED, "1")


ERPNEXT_SETTINGS = "ERPNext CRM Settings"


def is_erpnext_customer_enabled() -> bool:
	"""Is CRM's own ERPNext bridge ("ERPNext CRM Settings" > Enabled) on?

	Gates the whole "set up this customer in ERPNext" section of the wizard: when
	off, the wizard behaves exactly as it did before this feature existed. Unlike
	``is_wizard_enabled`` there is no separate switch of our own to invent — this
	reuses the toggle CRM itself already ships and the site owner already set.
	"""
	if not frappe.db.exists("DocType", ERPNEXT_SETTINGS):
		return False
	return bool(cint(frappe.db.get_single_value(ERPNEXT_SETTINGS, "enabled")))


def get_site_properties() -> dict:
	"""What CRM itself follows: language, time zone, System Settings formats, currency, branding."""
	from frappe.utils import get_system_timezone
	from frappe.utils.jinja_globals import is_rtl

	system = frappe.get_system_settings
	currency = frappe.db.get_single_value(SETTINGS, "currency") or frappe.db.get_default("currency")

	return {
		"lang": frappe.local.lang,
		"rtl": bool(is_rtl()),
		"timezone": {
			"system": get_system_timezone(),
			"user": frappe.db.get_value("User", frappe.session.user, "time_zone") or get_system_timezone(),
		},
		"date_format": system("date_format") or "yyyy-mm-dd",
		"time_format": system("time_format") or "HH:mm:ss",
		"number_format": system("number_format") or "#,###.##",
		"float_precision": cint(system("float_precision")) or 3,
		"currency_precision": cint(system("currency_precision")) or 2,
		"first_day_of_the_week": system("first_day_of_the_week") or "Monday",
		"currency": currency,
		"currency_symbol": (frappe.db.get_value("Currency", currency, "symbol") if currency else None)
		or currency,
		"brand": {
			"name": frappe.db.get_single_value(SETTINGS, "brand_name") or None,
			"logo": frappe.db.get_single_value(SETTINGS, "brand_logo") or None,
			"favicon": frappe.db.get_single_value(SETTINGS, "favicon") or None,
		},
	}
