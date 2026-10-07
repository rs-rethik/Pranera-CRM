"""Data for the country-code picker that crm_phone_ext.js adds to CRM's phone fields.

CRM draws every field whose ``options`` is "Phone" as a plain text box. The picker
needs two things CRM's page doesn't have: which labels on a form are phone fields
(the rendered markup carries no fieldname), and the list of country dial codes.
"""

import re

import frappe
from frappe import _
from frappe.geo.country_info import get_all

# the CRM forms whose fields are drawn by CRM's FieldLayout (custom fields included)
DOCTYPES = ("CRM Lead", "CRM Deal", "Contact", "CRM Organization")


@frappe.whitelist()
def get_phone_picker_data() -> dict:
	"""Phone field labels, country dial codes and the site's default country."""
	return {
		"labels": get_phone_field_labels(),
		"countries": get_countries(),
		"default_country": get_default_country_code(),
	}


def get_phone_field_labels() -> list[str]:
	labels = set()
	for doctype in DOCTYPES:
		for field in frappe.get_meta(doctype).fields:
			if field.fieldtype == "Phone" or field.options == "Phone":
				labels.add(_(field.label))
	return sorted(labels)


def get_countries() -> list[dict]:
	countries = []
	for name, info in get_all().items():
		isd = normalize_isd(info.get("isd"))
		if isd and info.get("code"):
			countries.append({"name": _(name), "code": info["code"], "isd": isd})
	return sorted(countries, key=lambda c: c["name"])


def normalize_isd(isd: str | None) -> str:
	"""'+1-684' -> '+1684'; '' when there is no usable code."""
	digits = re.sub(r"\D", "", isd or "")
	return f"+{digits}" if digits else ""


def get_default_country_code() -> str | None:
	country = frappe.db.get_single_value("System Settings", "country")
	return (get_all().get(country) or {}).get("code") if country else None
