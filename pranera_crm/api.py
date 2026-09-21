"""Backend for the Pranera CRM "Convert to Deal" wizard.

Everything here is a thin, permission-aware layer over Frappe CRM. The actual
conversion is delegated to CRM's own ``convert_to_deal``; we only add what it
lacks: an "already converted" guard, server-side validation of the payload and
the ability to edit the data a *new* Organization / Contact is built from.
"""

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import cint

from crm.fcrm.doctype.crm_fields_layout.crm_fields_layout import get_fields_layout
from crm.fcrm.doctype.crm_lead.crm_lead import convert_to_deal

LEAD = "CRM Lead"
DEAL = "CRM Deal"
ORGANIZATION = "CRM Organization"

# The Lead fields CRM builds a *new* Organization / Contact from
# (see CRMLead.create_organization / create_contact).
ORGANIZATION_FIELDS = (
	"organization",
	"website",
	"territory",
	"industry",
	"annual_revenue",
	"no_of_employees",
)
CONTACT_FIELDS = (
	"salutation",
	"first_name",
	"last_name",
	"gender",
	"job_title",
	"email",
	"phone",
	"mobile_no",
)

# Deal keys the wizard must never let a client set: they are derived by CRM
# from the lead / the org and contact chosen in the wizard.
PROTECTED_DEAL_FIELDS = frozenset(
	{
		"name",
		"doctype",
		"naming_series",
		"lead",
		"contacts",
		"organization",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"docstatus",
		"idx",
		"parent",
		"parenttype",
		"parentfield",
	}
)

# Mirrors ConvertToDealModal.vue
LEAD_DEAL_FIELD_MAP = {"deal_owner": "lead_owner"}
SKIP_PREFILL_FIELDS = ("organization", "status")
LAYOUT_FIELD_TYPES_TO_SKIP = ("Tab Break", "Section Break", "Column Break", "HTML", "Button", "Table")


class LeadAlreadyConverted(frappe.ValidationError):
	pass


# --------------------------------------------------------------------------- #
# Context
# --------------------------------------------------------------------------- #


@frappe.whitelist(allow_guest=True)
def whoami() -> str:
	"""The session's user. Guests may call it: that is how the SPA tells an expired
	session (``Guest``) apart from a genuine permission error, since Frappe's own
	``frappe.auth.get_logged_user`` isn't callable by guests."""
	return frappe.session.user


@frappe.whitelist()
def get_wizard_context(lead: str) -> dict:
	"""Everything the wizard needs to render for ``lead`` in one round trip."""
	_get_lead_for_read(lead)
	doc = frappe.get_doc(LEAD, lead)

	lead_data = {
		df.fieldname: doc.get(df.fieldname)
		for df in doc.meta.fields
		if df.fieldtype not in frappe.model.no_value_fields and doc.get(df.fieldname) not in (None, "")
	}
	lead_data["name"] = doc.name
	# lets the wizard tell a saved draft was made against an older version of the lead
	lead_data["modified"] = str(doc.modified)
	lead_data["lead_name"] = doc.lead_name or doc.first_name

	layout = get_fields_layout(DEAL, "Required Fields")
	layout_fields = _flatten_layout(layout)

	deal = _deal_for_lead(doc.name)
	status_type = frappe.get_cached_value("CRM Lead Status", doc.status, "type") if doc.status else None

	return {
		"lead": lead_data,
		"converted": bool(cint(doc.converted) or deal),
		"deal": deal,
		"lost": status_type == "Lost",
		"can_write": frappe.has_permission(LEAD, "write", doc.name),
		"candidates": find_candidates(
			organization=doc.organization,
			website=doc.website,
			email=doc.email,
			phone=doc.phone,
			mobile_no=doc.mobile_no,
		),
		"organization_fields": _field_meta(ORGANIZATION_FIELDS),
		"contact_fields": _field_meta(CONTACT_FIELDS),
		"deal_layout": layout,
		"deal_defaults": _deal_defaults(doc, layout_fields),
		"deal_statuses": frappe.get_all(
			"CRM Deal Status",
			fields=["name", "color", "type", "position"],
			order_by="position asc",
		),
	}


@frappe.whitelist()
def search_candidates(
	lead: str,
	organization: str | None = None,
	website: str | None = None,
	email: str | None = None,
	phone: str | None = None,
	mobile_no: str | None = None,
) -> dict:
	"""Re-run the match lookup for values the user edited in the wizard."""
	_get_lead_for_read(lead)
	return find_candidates(
		organization=organization, website=website, email=email, phone=phone, mobile_no=mobile_no
	)


def find_candidates(
	organization=None, website=None, email=None, phone=None, mobile_no=None
) -> dict:
	"""Existing Organizations / Contacts that look like the lead.

	``auto_organization`` / ``auto_contact`` are what CRM's ``convert_to_deal``
	would silently reuse when the caller does *not* pick an existing record, so
	the UI can warn about it. They follow CRM's own precedence.
	"""
	organizations = _organization_candidates(organization, website)
	contacts, auto_contact = _contact_candidates(email, phone, mobile_no)

	auto_organization = None
	if organization and frappe.db.exists(ORGANIZATION, {"organization_name": organization}):
		auto_organization = frappe.db.get_value(ORGANIZATION, {"organization_name": organization}, "name")

	return {
		"organizations": organizations,
		"contacts": contacts,
		"auto_organization": auto_organization,
		"auto_contact": auto_contact,
	}


def _organization_candidates(organization, website):
	names = {}

	if organization:
		for row in frappe.get_list(
			ORGANIZATION,
			filters={"organization_name": ["like", f"%{organization.strip()}%"]},
			fields=["name", "organization_name", "website", "industry", "territory"],
			limit=10,
		):
			exact = (row.organization_name or "").strip().lower() == organization.strip().lower()
			names[row.name] = {**row, "reason": "name", "exact": exact}

	domain = _domain(website)
	if domain:
		for row in frappe.get_list(
			ORGANIZATION,
			filters={"website": ["like", f"%{domain}%"]},
			fields=["name", "organization_name", "website", "industry", "territory"],
			limit=10,
		):
			if row.name in names:
				names[row.name]["reason"] = "name and website"
			else:
				names[row.name] = {**row, "reason": "website", "exact": False}

	# exact matches first
	return sorted(names.values(), key=lambda r: (not r["exact"], r["organization_name"] or ""))


def _contact_candidates(email, phone, mobile_no):
	"""Returns (permitted candidate list, contact CRM would auto-link)."""
	parents: dict[str, str] = {}
	auto_contact = None

	# Same lookup order as CRMLead.contact_exists: email, then phone, then mobile.
	lookups = (
		("Contact Email", "email_id", email, "email"),
		("Contact Phone", "phone", phone, "phone"),
		("Contact Phone", "phone", mobile_no, "mobile"),
	)
	for doctype, fieldname, value, reason in lookups:
		if not value:
			continue
		for parent in frappe.get_all(
			doctype, filters={fieldname: value, "parenttype": "Contact"}, pluck="parent"
		):
			parents.setdefault(parent, reason)
			if auto_contact is None:
				auto_contact = parent

	rows = []
	if parents:
		rows = frappe.get_list(
			"Contact",
			filters={"name": ["in", list(parents)]},
			fields=["name", "first_name", "last_name", "email_id", "mobile_no", "company_name"],
			limit=10,
		)
	permitted = {r.name for r in rows}
	contacts = [{**r, "reason": parents[r.name]} for r in rows]
	if auto_contact not in permitted:
		auto_contact = None
	return contacts, auto_contact


def _domain(website):
	if not website:
		return None
	website = website.strip()
	host = urlparse(website if "//" in website else f"//{website}").netloc or website
	host = host.lower().removeprefix("www.")
	return host or None


# --------------------------------------------------------------------------- #
# Convert
# --------------------------------------------------------------------------- #


@frappe.whitelist(methods=["POST"])
def convert(
	lead: str,
	deal: str | dict | None = None,
	existing_contact: str | None = None,
	existing_organization: str | None = None,
	lead_updates: str | dict | None = None,
) -> str:
	"""Convert ``lead`` into a Deal via CRM's ``convert_to_deal``; returns the Deal name.

	``lead_updates`` are applied to the Lead first (permission-checked) because CRM
	builds a *new* Organization / Contact purely from the Lead's own fields.
	Everything runs in the request's single transaction, so a failure anywhere
	rolls the lead edits and the ``converted`` flag back too.
	"""
	if not frappe.db.exists(LEAD, lead):
		frappe.throw(_("Lead {0} does not exist").format(lead), frappe.DoesNotExistError)

	if not frappe.has_permission(LEAD, "write", lead):
		frappe.throw(_("Not allowed to convert Lead to Deal"), frappe.PermissionError)

	# Serialise concurrent submits (double tap, two tabs) so a lead can't be
	# converted twice.
	state = frappe.db.get_value(LEAD, lead, ["converted", "status"], as_dict=True, for_update=True)
	_ensure_convertible(lead, state)

	existing_contact = existing_contact or None
	existing_organization = existing_organization or None
	_validate_existing_record("Contact", existing_contact)
	_validate_existing_record(ORGANIZATION, existing_organization)

	layout_fields = _flatten_layout(get_fields_layout(DEAL, "Required Fields"))
	deal_values = _clean_deal(deal, layout_fields)

	lead_doc = frappe.get_doc(LEAD, lead)
	_check_required_deal_fields(lead_doc, layout_fields, deal_values)
	_apply_lead_updates(
		lead_doc,
		lead_updates,
		skip_organization=bool(existing_organization),
		skip_contact=bool(existing_contact),
	)

	return convert_to_deal(
		lead=lead,
		deal=deal_values,
		existing_contact=existing_contact,
		existing_organization=existing_organization,
	)


def _ensure_convertible(lead, state):
	deal = _deal_for_lead(lead)
	if cint(state.converted) or deal:
		frappe.throw(
			_("Lead {0} is already converted{1}").format(lead, f" to Deal {deal}" if deal else ""),
			LeadAlreadyConverted,
			title=_("Already Converted"),
		)

	if state.status and frappe.get_cached_value("CRM Lead Status", state.status, "type") == "Lost":
		frappe.throw(_("Cannot convert a lead with status {0}").format(state.status))


def _validate_existing_record(doctype, name):
	if not name:
		return
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} does not exist").format(_(doctype), name), frappe.DoesNotExistError)
	if not frappe.has_permission(doctype, "read", name):
		frappe.throw(
			_("You do not have permission to use {0} {1}").format(_(doctype), name),
			frappe.PermissionError,
		)


def _clean_deal(deal, layout_fields) -> dict:
	"""Keep only fields from the Deal quick-entry layout, minus protected ones."""
	deal = frappe.parse_json(deal) if isinstance(deal, str) else (deal or {})
	if not isinstance(deal, dict):
		frappe.throw(_("Invalid deal data"))

	allowed = {f.fieldname for f in layout_fields} - PROTECTED_DEAL_FIELDS
	return {k: v for k, v in deal.items() if k in allowed}


def _check_required_deal_fields(lead_doc, layout_fields, deal_values):
	defaults = _deal_defaults(lead_doc, layout_fields)
	missing = []
	for field in layout_fields:
		if not field.reqd or field.fieldname in PROTECTED_DEAL_FIELDS:
			continue
		value = deal_values.get(field.fieldname, defaults.get(field.fieldname))
		if value in (None, "") and field.fieldtype != "Check":
			missing.append(_(field.label or field.fieldname))

	if missing:
		frappe.throw(
			_("Missing required Deal fields: {0}").format(", ".join(missing)), frappe.MandatoryError
		)


def _apply_lead_updates(lead_doc, lead_updates, skip_organization, skip_contact):
	updates = frappe.parse_json(lead_updates) if isinstance(lead_updates, str) else (lead_updates or {})
	if not isinstance(updates, dict):
		frappe.throw(_("Invalid lead updates"))

	allowed = set()
	if not skip_organization:
		allowed.update(ORGANIZATION_FIELDS)
	if not skip_contact:
		allowed.update(CONTACT_FIELDS)

	changes = {}
	for fieldname, value in updates.items():
		if fieldname not in allowed:
			continue
		value = None if value == "" else value
		if (lead_doc.get(fieldname) or None) != value:
			changes[fieldname] = value

	if not changes:
		return

	lead_doc.update(changes)
	# save() enforces write permission and runs CRM's own validations
	lead_doc.save()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_lead_for_read(lead):
	if not frappe.db.exists(LEAD, lead):
		frappe.throw(_("Lead {0} does not exist").format(lead), frappe.DoesNotExistError)
	if not frappe.has_permission(LEAD, "read", lead):
		frappe.throw(_("You do not have permission to access this Lead"), frappe.PermissionError)


def _deal_for_lead(lead):
	return frappe.db.get_value(DEAL, {"lead": lead}, "name")


def _flatten_layout(tabs) -> list:
	"""All field dicts in a quick-entry layout, in display order."""
	fields = []
	for tab in tabs or []:
		for section in tab.get("sections") or []:
			for column in section.get("columns") or []:
				for field in column.get("fields") or []:
					if isinstance(field, dict) and field.get("fieldtype") not in LAYOUT_FIELD_TYPES_TO_SKIP:
						fields.append(frappe._dict(field))
	return fields


def _field_meta(fieldnames):
	meta = frappe.get_meta(LEAD)
	out = []
	for fieldname in fieldnames:
		df = meta.get_field(fieldname)
		if not df:
			continue
		out.append(
			{
				"fieldname": df.fieldname,
				"label": _(df.label),
				"fieldtype": df.fieldtype,
				"options": df.options,
				"reqd": cint(df.reqd),
			}
		)
	return out


def _deal_defaults(lead_doc, layout_fields) -> dict:
	"""Prefill Deal fields from the lead using the same rules as CRM's modal."""
	lead_meta = frappe.get_meta(LEAD)
	lead_fieldnames = {df.fieldname for df in lead_meta.fields}
	defaults = {}

	for field in layout_fields:
		if field.fieldname in SKIP_PREFILL_FIELDS:
			continue

		lead_fieldname = LEAD_DEAL_FIELD_MAP.get(field.fieldname)
		if not lead_fieldname and field.fieldname in lead_fieldnames:
			lead_fieldname = field.fieldname
		if not lead_fieldname:
			lead_fieldname = _matching_custom_lead_field(lead_meta, field)
		if not lead_fieldname:
			continue

		value = lead_doc.get(lead_fieldname)
		if value not in (None, ""):
			defaults[field.fieldname] = value

	return defaults


def _is_custom(field) -> bool:
	fieldname = field.get("fieldname") or ""
	return bool(
		field.get("is_custom_field")
		or field.get("custom")
		or fieldname.startswith("custom_")
		or (field.get("name") and field.get("name") == f"{field.get('parent')}-{fieldname}")
	)


def _matching_custom_lead_field(lead_meta, deal_field):
	if not _is_custom(deal_field):
		return None
	matches = [
		lf.fieldname
		for lf in lead_meta.fields
		if _is_custom(lf) and lf.label == deal_field.get("label") and lf.fieldtype == deal_field.get("fieldtype")
	]
	return matches[0] if len(matches) == 1 else None
