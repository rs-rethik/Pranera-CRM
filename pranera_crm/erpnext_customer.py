"""Creates (or links) the ERPNext Customer/Address/Contact for a converted Deal.

Runs *after* ``convert_to_deal`` has already committed the CRM Deal/Organization/
Contact (see ``pranera_crm.api.convert``): a failure here never undoes that
conversion, it only reports a clear, specific error for the caller to surface and
let the user retry. See the "Two-phase commit" deviation in the project plan.

Every ERPNext link field this module sets comes from ``pranera_crm.customer_wizard``
resolving the user's plain-language answers against the admin-configured
``Customer Wizard Mapping`` rows — nothing here hardcodes a Customer Group,
Territory, GST Category, or similar business value.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint

from pranera_crm import customer_wizard as cw

CUSTOMER = "Customer"
ADDRESS = "Address"
CONTACT = "Contact"
DEAL = "CRM Deal"
ORGANIZATION = "CRM Organization"

# Plain fields the user types directly (not resolved from a mapping question).
ADDRESS_INPUT_FIELDS = ("address_line1", "address_line2", "city", "pincode", "country", "state", "gstin")

# Used only when india_compliance isn't installed, to give the same format check
# its own validators would have made.
GSTIN_FORMAT = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class DuplicateCustomerName(Exception):
	"""Raised to signal the caller should ask the user to confirm reusing an existing Customer."""

	def __init__(self, existing_customer):
		self.existing_customer = existing_customer
		super().__init__(existing_customer)


def address_field_meta() -> list[dict]:
	"""Live field metadata for the plain (non-question) Address inputs, same pattern
	as ``pranera_crm.api._field_meta`` uses for the Organization/Contact steps."""
	meta = frappe.get_meta(ADDRESS)
	out = []
	for fieldname in ADDRESS_INPUT_FIELDS:
		df = meta.get_field(fieldname)
		if not df:
			continue
		out.append(
			{
				"fieldname": df.fieldname,
				"label": _(df.label or df.fieldname),
				"fieldtype": df.fieldtype,
				"options": df.options,
				"reqd": cint(df.reqd),
			}
		)
	return out


@frappe.whitelist()
def lookup_gstin(gstin: str) -> dict:
	"""Fetch the registered business name and address for a GSTIN from the GST
	public search (via india_compliance), so the user doesn't have to type them.

	Only the values the caller asked to auto-fill are read from the response —
	nothing here is written to any doctype directly. The organization/address the
	user reviews and submits are still whatever ends up in the wizard's form.
	"""
	try:
		from india_compliance.gst_india.utils.gstin_info import get_gstin_info
	except ImportError:
		frappe.throw(_("GSTIN lookup needs the India Compliance app, which isn't installed."))

	if not frappe.has_permission(CUSTOMER, "read"):
		frappe.throw(_("Not allowed"), frappe.PermissionError)

	info = get_gstin_info(gstin, throw_error=True)
	address = info.get("permanent_address") or {}
	return {
		"business_name": info.get("business_name") or "",
		"gst_category": info.get("gst_category") or "",
		"status": info.get("status") or "",
		"address": {
			"address_line1": address.get("address_line1") or "",
			"address_line2": address.get("address_line2") or "",
			"city": address.get("city") or "",
			"state": address.get("state") or "",
			"pincode": address.get("pincode") or "",
			"country": address.get("country") or "India",
		},
	}


def get_context(organization: str | None) -> dict:
	"""Everything the wizard needs to render the "set up this customer in ERPNext"
	section: whether it applies, the live questions, and a heads-up if a Customer
	with this name already exists."""
	from pranera_crm.settings import is_erpnext_customer_enabled

	enabled = is_erpnext_customer_enabled()
	if not enabled:
		return {"enabled": False}

	return {
		"enabled": True,
		"organization_questions": cw.all_questions_payload("Organization"),
		"contact_questions": cw.all_questions_payload("Contact"),
		"address_fields": address_field_meta(),
		"existing_customer": (
			frappe.db.exists(CUSTOMER, {"customer_name": organization}) if organization else None
		),
	}


@frappe.whitelist()
def refresh_questions(scope: str, answers: str | dict | None = None) -> list[dict]:
	"""Re-resolve live (Dynamic) options as the user answers earlier questions,
	e.g. suggest Sales Persons once Territory is known."""
	from pranera_crm.settings import is_erpnext_customer_enabled

	if not is_erpnext_customer_enabled():
		frappe.throw(_("ERPNext integration is turned off in CRM Settings."))
	if scope not in ("Organization", "Contact"):
		frappe.throw(_("Invalid scope"))

	answers = frappe.parse_json(answers) if isinstance(answers, str) else (answers or {})
	return cw.scope_payload(scope, answers)


def create(
	*,
	deal: str,
	organization_answers: dict,
	contact_answers: dict,
	address: dict,
	overrides: dict | None = None,
	confirm_duplicate: bool = False,
) -> dict:
	"""All-or-nothing: creates/updates the Customer, its Address and Contact, and
	cross-links them to ``deal``. Returns ``{"customer": name}``.

	Raises ``DuplicateCustomerName`` when a Customer with the resolved name already
	exists and ``confirm_duplicate`` wasn't set — the caller re-asks the user and
	resubmits with it set to reuse (link to) that Customer instead of creating one.
	Any other failure raises normally; the caller is responsible for the rollback
	boundary (this function does not commit or roll back on its own).
	"""
	deal_doc = frappe.get_doc(DEAL, deal)
	org_doc = frappe.get_doc(ORGANIZATION, deal_doc.organization) if deal_doc.organization else None

	org_result = cw.resolve("Organization", organization_answers, overrides)
	contact_result = cw.resolve("Contact", contact_answers, overrides)
	_validate_resolved_fields(org_result["fields"])
	_validate_resolved_fields(contact_result["fields"])
	_validate_gst(org_result["fields"].get(CUSTOMER, {}), org_result["fields"].get(ADDRESS, {}), address)
	_mirror_gst_category_to_customer(org_result["fields"])

	customer_name = (deal_doc.organization or "").strip() or _primary_contact_full_name(deal_doc)
	if not customer_name:
		frappe.throw(_("An organization or a primary contact is needed to name the Customer."))

	existing = frappe.db.exists(CUSTOMER, {"customer_name": customer_name})
	if existing and not confirm_duplicate:
		raise DuplicateCustomerName(existing)

	# same GSTIN on another customer's address is almost always the same business
	# entered twice; reuse happens through the duplicate-name flow, not silently
	gstin = (address or {}).get("gstin")
	if gstin:
		_validate_gstin_duplicate(gstin, exclude=existing)

	customer = frappe.get_doc(CUSTOMER, existing) if existing else frappe.new_doc(CUSTOMER)
	customer.customer_name = customer_name
	customer.update(org_result["fields"].get(CUSTOMER, {}))
	_apply_sales_team(customer, org_result["sales_persons"])

	address_name = _upsert_address(org_doc, customer_name, address, org_result["fields"].get(ADDRESS, {}))
	if address_name and not customer.customer_primary_address:
		customer.customer_primary_address = address_name

	contact_name = _primary_contact_name(deal_doc)
	if contact_name:
		_apply_contact_updates(contact_name, contact_result["fields"].get(CONTACT, {}))
		if not customer.customer_primary_contact:
			customer.customer_primary_contact = contact_name

	if frappe.get_meta(CUSTOMER).has_field("crm_deal"):
		customer.crm_deal = deal

	if existing:
		customer.save()
	else:
		customer.insert()

	if contact_name:
		_link_party(CONTACT, contact_name, CUSTOMER, customer.name)
	if address_name:
		_link_party(ADDRESS, address_name, CUSTOMER, customer.name)

	if frappe.get_meta(DEAL).has_field("erpnext_customer"):
		frappe.db.set_value(DEAL, deal, "erpnext_customer", customer.name)

	return {
		"customer": customer.name,
		"organization_review": org_result["review"],
		"contact_review": contact_result["review"],
	}


def _validate_resolved_fields(fields_by_doctype: dict):
	"""Every resolved/overridden value must be something the target field can
	actually hold: Link values must exist as records, Select values must be one
	of the field's options. A mis-configured mapping (or a tampered override
	value) is blocked here instead of failing deep inside insert()."""
	for doctype, fields in fields_by_doctype.items():
		meta = frappe.get_meta(doctype)
		for fieldname, value in fields.items():
			field = meta.get_field(fieldname)
			if not field or not value:
				continue
			if field.fieldtype == "Link":
				if not frappe.db.exists(field.options, value):
					frappe.throw(
						_("{0} {1} does not exist (from {2}.{3})").format(
							_(field.options), value, doctype, fieldname
						)
					)
			elif field.fieldtype == "Select":
				options = [o.strip() for o in (field.options or "").split("\n") if o.strip()]
				if options and value not in options:
					frappe.throw(
						_("{0} is not a valid value for {1}.{2}").format(value, doctype, fieldname)
					)


def _mirror_gst_category_to_customer(fields_by_doctype: dict):
	"""GST Category questions naturally target the Address (a business can be
	registered differently per location); Customer.gst_category is a required,
	denormalised copy, so mirror the Address's resolved value onto it unless a
	question targets Customer.gst_category directly."""
	address_gst = fields_by_doctype.get(ADDRESS, {}).get("gst_category")
	if not address_gst:
		return
	fields_by_doctype.setdefault(CUSTOMER, {}).setdefault("gst_category", address_gst)


def _validate_gst(customer_fields: dict, address_fields: dict, address_input: dict):
	gstin = (address_input or {}).get("gstin")
	if gstin:
		try:
			from india_compliance.gst_india.utils import validate_gstin

			validate_gstin(gstin)
		except ImportError:
			# no canonical validators without the app; still enforce the format
			if not GSTIN_FORMAT.match(gstin):
				frappe.throw(_("{0} is not a valid GSTIN").format(gstin))

	gst_category = None
	try:
		from india_compliance.gst_india.utils import validate_gst_category

		gst_category = address_fields.get("gst_category") or customer_fields.get("gst_category")
		if gst_category:
			validate_gst_category(gst_category, gstin)
	except ImportError:
		return


def _validate_gstin_duplicate(gstin: str, exclude: str | None):
	"""Block a GSTIN that already belongs to a *different* Customer's address
	(GSTINs live on Address; several customers sharing one is a decision an
	admin makes deliberately in ERPNext, not through the wizard)."""
	others = [name for name in _customers_with_gstin(gstin) if name != exclude]
	if others:
		frappe.throw(
			_("GSTIN {0} is already used by customer {1}").format(gstin, ", ".join(others)),
			title=_("Possible Duplicate"),
		)


def _customers_with_gstin(gstin: str) -> list[str]:
	names: list[str] = []
	addresses = frappe.get_all(ADDRESS, filters={"gstin": gstin}, pluck="name")
	if addresses:
		names = frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": ADDRESS, "parent": ["in", addresses], "link_doctype": CUSTOMER},
			pluck="link_name",
		)
	if frappe.get_meta(CUSTOMER).has_field("gstin"):
		names += frappe.get_all(CUSTOMER, filters={"gstin": gstin}, pluck="name")
	return sorted(set(names))


def _primary_contact_name(deal_doc) -> str | None:
	if not deal_doc.contacts:
		return None
	primary = next((c for c in deal_doc.contacts if c.is_primary), deal_doc.contacts[0])
	return primary.contact


def _primary_contact_full_name(deal_doc) -> str | None:
	if not deal_doc.contacts:
		return None
	primary = next((c for c in deal_doc.contacts if c.is_primary), deal_doc.contacts[0])
	return primary.full_name or None


def _apply_sales_team(customer, sales_persons: list[str]):
	if not sales_persons:
		return
	existing = {row.sales_person for row in (customer.sales_team or [])}
	for sales_person in sales_persons:
		if sales_person in existing:
			continue
		if not frappe.db.exists("Sales Person", {"name": sales_person, "enabled": 1}):
			continue
		customer.append("sales_team", {"sales_person": sales_person, "allocated_percentage": 100})
		existing.add(sales_person)


def _upsert_address(org_doc, title: str, address_input: dict, address_question_fields: dict) -> str | None:
	"""Reuses the CRM Organization's existing Address if it has one; otherwise creates
	one from the collected fields. Returns ``None`` if there is nothing to save (the
	address section was left blank and the organization has no address yet)."""
	address_input = address_input or {}
	has_input = bool(address_input.get("address_line1"))

	if org_doc and org_doc.address:
		if has_input or address_question_fields:
			addr = frappe.get_doc(ADDRESS, org_doc.address)
			for fieldname in ADDRESS_INPUT_FIELDS:
				if address_input.get(fieldname):
					addr.set(fieldname, address_input[fieldname])
			addr.update(address_question_fields)
			addr.save()
		return org_doc.address

	if not has_input:
		return None

	addr = frappe.new_doc(ADDRESS)
	addr.address_title = title
	for fieldname in ADDRESS_INPUT_FIELDS:
		if address_input.get(fieldname):
			addr.set(fieldname, address_input[fieldname])
	addr.update(address_question_fields)
	# address_type is mandatory in core; a "What is this address for?" mapping question
	# (scope=Organization, target Address.address_type) normally supplies it, but a
	# site that hasn't configured one yet still needs a valid, harmless default.
	addr.address_type = addr.address_type or "Billing"
	if org_doc:
		addr.append("links", {"link_doctype": ORGANIZATION, "link_name": org_doc.name})
	addr.insert()

	if org_doc and not org_doc.address:
		frappe.db.set_value(ORGANIZATION, org_doc.name, "address", addr.name)

	return addr.name


def _apply_contact_updates(contact_name: str, contact_fields: dict):
	if not contact_fields:
		return
	contact = frappe.get_doc(CONTACT, contact_name)
	contact.update(contact_fields)
	contact.save()


def _link_party(doctype: str, name: str, link_doctype: str, link_name: str):
	"""Append a Dynamic Link row for ``link_doctype``/``link_name`` unless already present."""
	doc = frappe.get_doc(doctype, name)
	already_linked = any(row.link_doctype == link_doctype and row.link_name == link_name for row in doc.links)
	if already_linked:
		return
	doc.append("links", {"link_doctype": link_doctype, "link_name": link_name, "link_title": link_name})
	doc.save()
