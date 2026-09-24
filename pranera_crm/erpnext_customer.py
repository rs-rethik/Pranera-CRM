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
from frappe.rate_limiter import rate_limit

from pranera_crm import customer_wizard as cw
from pranera_crm.utils import field_meta

CUSTOMER = "Customer"
ADDRESS = "Address"
CONTACT = "Contact"
DEAL = "CRM Deal"
ORGANIZATION = "CRM Organization"

ADDRESS_INPUT_FIELDS = ("address_line1", "address_line2", "city", "pincode", "country", "state", "gstin")

GSTIN_FORMAT = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class DuplicateCustomerName(Exception):
	"""Raised to signal the caller should ask the user to confirm reusing an existing Customer."""

	def __init__(self, existing_customer):
		self.existing_customer = existing_customer
		super().__init__(existing_customer)


def address_field_meta() -> list[dict]:
	"""Live field metadata for the plain (non-question) Address inputs, same
	``pranera_crm.utils.field_meta`` the Organization/Contact steps use."""
	return field_meta(ADDRESS, ADDRESS_INPUT_FIELDS)


GSTIN_LOOKUP_CACHE_PREFIX = "pranera_crm_gstin_lookup_"
GSTIN_LOOKUP_CACHE_TTL = 86400


@frappe.whitelist()
@rate_limit(limit=20, seconds=300, methods=["POST"])
def lookup_gstin(gstin: str) -> dict:
	"""Fetch the registered business name and address for a GSTIN from the GST
	public search (via india_compliance), so the user doesn't have to type them.

	Only the values the caller asked to auto-fill are read from the response —
	nothing here is written to any doctype directly. The organization/address the
	user reviews and submits are still whatever ends up in the wizard's form.

	Cached by GSTIN (not by user — the same GSTIN resolves to the same business
	data for everyone) so re-fetching one already looked up never hits the external
	API again, and rate-limited (20 lookups per 5 minutes per user/IP) so this
	whitelisted endpoint can't be used to probe an unbounded list of GSTINs.
	"""
	try:
		from india_compliance.gst_india.utils.gstin_info import get_gstin_info
	except ImportError:
		frappe.throw(_("GSTIN lookup needs the India Compliance app, which isn't installed."))

	if not frappe.has_permission(CUSTOMER, "read"):
		frappe.throw(_("Not allowed"), frappe.PermissionError)

	cache_key = GSTIN_LOOKUP_CACHE_PREFIX + gstin
	cached = frappe.cache.get_value(cache_key, expires=True)
	if cached is not None:
		return cached

	info = get_gstin_info(gstin, throw_error=True)
	address = info.get("permanent_address") or {}
	result = {
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
	frappe.cache.set_value(cache_key, result, expires_in_sec=GSTIN_LOOKUP_CACHE_TTL)
	return result


def get_context(organization: str | None) -> dict:
	"""Everything the wizard needs to render the Organization/Contact steps' question-
	driven fields, and (when the ERPNext bridge is on) the "set up this customer in
	ERPNext" section: whether it applies, the live questions, and a heads-up if a
	Customer with this name already exists.

	``organization_questions``/``contact_questions`` are always returned, bridge on or
	off: some questions (Territory, Industry, ...) apply regardless of the bridge —
	see ``requires_erpnext_bridge`` on ``Customer Wizard Mapping``. Only the
	ERPNext-only questions, and the Address/duplicate-Customer fields, are left out
	when the bridge is off."""
	from pranera_crm.settings import is_erpnext_customer_enabled

	enabled = is_erpnext_customer_enabled()

	return {
		"enabled": enabled,
		"organization_questions": cw.all_questions_payload("Organization", include_bridge_questions=enabled),
		"contact_questions": cw.all_questions_payload("Contact", include_bridge_questions=enabled),
		"address_fields": address_field_meta() if enabled else [],
		"existing_customer": (
			frappe.db.exists(CUSTOMER, {"customer_name": organization}) if organization and enabled else None
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


def _already_linked_customer(deal: str, deal_doc) -> str | None:
	"""A Customer already cross-linked to this Deal, if any (and still real) —
	e.g. by CRM's own ERPNext bridge, if an admin has it on despite pranera_crm
	defaulting it off (see setup.ensure_erpnext_customer_sync_disabled). Guarded
	with has_field like every other crm_deal/erpnext_customer touch in this
	module: both are CRM's own custom fields, not guaranteed on every version."""
	linked = None
	if frappe.get_meta(CUSTOMER).has_field("crm_deal"):
		linked = frappe.db.exists(CUSTOMER, {"crm_deal": deal})
	if not linked and frappe.get_meta(DEAL).has_field("erpnext_customer"):
		linked = deal_doc.get("erpnext_customer") or None
	if linked and not frappe.db.exists(CUSTOMER, linked):
		return None
	return linked


def create(
	*,
	deal: str,
	organization_answers: dict,
	contact_answers: dict,
	address: dict,
	overrides: dict | None = None,
	confirm_duplicate: bool = False,
	existing_address: str | None = None,
	org_result: dict | None = None,
	contact_result: dict | None = None,
) -> dict:
	"""All-or-nothing: creates/updates the Customer, its Address and Contact, and
	cross-links them to ``deal``. Returns ``{"customer": name}``.

	Raises ``DuplicateCustomerName`` when a Customer with the resolved name already
	exists and ``confirm_duplicate`` wasn't set — the caller re-asks the user and
	resubmits with it set to reuse (link to) that Customer instead of creating one.
	Any other failure raises normally; the caller is responsible for the rollback
	boundary (this function does not commit or roll back on its own).

	``existing_address`` (validated by the caller) skips address creation entirely
	and reuses that record instead — see ``_upsert_address``.

	``org_result``/``contact_result``: pass already-resolved ``cw.resolve()``
	output when the caller (``api.convert()``) computed it moments ago from the
	same answers/overrides, so this doesn't redundantly resolve both scopes a
	second time in the same request. ``None`` (e.g. the standalone retry endpoint,
	a separate later request) resolves fresh here, same as always.
	"""
	deal_doc = frappe.get_doc(DEAL, deal)
	org_doc = frappe.get_doc(ORGANIZATION, deal_doc.organization) if deal_doc.organization else None

	org_result = org_result or cw.resolve("Organization", organization_answers, overrides)
	contact_result = contact_result or cw.resolve("Contact", contact_answers, overrides)
	_validate_resolved_fields(org_result["fields"])
	_validate_resolved_fields(contact_result["fields"])
	_validate_gst(org_result["fields"].get(CUSTOMER, {}), org_result["fields"].get(ADDRESS, {}), address)
	_mirror_gst_category_to_customer(org_result["fields"])

	customer_name = (deal_doc.organization or "").strip() or _primary_contact_full_name(deal_doc)
	if not customer_name:
		frappe.throw(_("An organization or a primary contact is needed to name the Customer."))

	existing = _already_linked_customer(deal, deal_doc)

	if not existing:
		existing = frappe.db.exists(CUSTOMER, {"customer_name": customer_name})
		if existing and not confirm_duplicate:
			raise DuplicateCustomerName(existing)

	gstin = (address or {}).get("gstin")
	if gstin:
		_validate_gstin_duplicate(gstin, exclude=existing)

	customer = frappe.get_doc(CUSTOMER, existing) if existing else frappe.new_doc(CUSTOMER)
	customer.customer_name = customer_name
	customer.update(org_result["fields"].get(CUSTOMER, {}))

	sales_persons = list(org_result["sales_persons"])
	auto_sales_person = _session_sales_person(frappe.session.user)
	if auto_sales_person and auto_sales_person not in sales_persons:
		sales_persons.append(auto_sales_person)
	_apply_sales_team(customer, sales_persons)

	if not existing:
		customer.disabled = 1

	contact_name = _primary_contact_name(deal_doc)
	if contact_name and not customer.customer_primary_contact:
		customer.customer_primary_contact = contact_name

	if frappe.get_meta(CUSTOMER).has_field("crm_deal"):
		customer.crm_deal = deal

	if existing:
		customer.save()
	else:
		customer.insert()

	address_name = _upsert_address(
		org_doc,
		customer_name,
		address,
		org_result["fields"].get(ADDRESS, {}),
		existing_address=existing_address,
		linked_customer=customer.name,
	)
	if address_name and not customer.customer_primary_address:
		frappe.db.set_value(CUSTOMER, customer.name, "customer_primary_address", address_name)

	if contact_name:
		_apply_contact_updates(
			contact_name, contact_result["fields"].get(CONTACT, {}), linked_customer=customer.name
		)

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
					frappe.throw(_("{0} is not a valid value for {1}.{2}").format(value, doctype, fieldname))


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
	"""Appends whichever of ``sales_persons`` aren't already on the Customer, split
	evenly across just the rows this call is adding — never touching the
	allocation of a row that was already there (e.g. an admin's own manual
	split), and never leaving two rows at 100% each when a question-resolved
	Sales Person and the auto session one both need adding at once. The new
	rows split whatever's left of 100 after the existing rows' own total, not a
	fresh 100 — ERPNext's own Customer.validate() requires every row (old and
	new together) to sum to exactly 100, so re-splitting a flat 100% across just
	the new rows would blow past that total the moment any row already existed."""
	if not sales_persons:
		return
	existing_rows = customer.sales_team or []
	existing = {row.sales_person for row in existing_rows}
	to_add = []
	for sales_person in sales_persons:
		if sales_person in existing or sales_person in to_add:
			continue
		if not frappe.db.exists("Sales Person", {"name": sales_person, "enabled": 1}):
			continue
		to_add.append(sales_person)
	if not to_add:
		return

	remaining = max(0, 100 - sum(row.allocated_percentage or 0 for row in existing_rows))
	share, remainder = divmod(remaining, len(to_add))
	for i, sales_person in enumerate(to_add):
		allocated = share + (1 if i < remainder else 0)
		customer.append("sales_team", {"sales_person": sales_person, "allocated_percentage": allocated})


def _session_sales_person(user: str) -> str | None:
	""" "Who handles this customer?" is never asked — it's whoever is running the
	wizard, found via the standard ERPNext link (User -> Employee.user_id ->
	Sales Person.employee). ``None`` if the acting user isn't linked to one (e.g.
	Administrator, or a user with no Employee/Sales Person record)."""
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		return None
	return frappe.db.get_value("Sales Person", {"employee": employee, "enabled": 1}, "name")


def _upsert_address(
	org_doc,
	title: str,
	address_input: dict,
	address_question_fields: dict,
	*,
	existing_address: str | None = None,
	linked_customer: str | None = None,
) -> str | None:
	"""Uses ``existing_address`` if the user picked one; otherwise reuses the CRM
	Organization's existing Address *only if the user didn't type a new one* —
	answered questions (Address Type, GST Category, ...) still apply onto it, but
	manually typed input (``address_line1`` given) always creates a new Address
	instead of silently mutating one that might be linked to, or shared with,
	other parties. The only way to *edit* an already-linked Address is to
	explicitly pick it via ``existing_address``. Returns ``None`` if there is
	nothing to save (the address section was left blank and the organization has
	no address yet).

	``linked_customer``, when given (the caller's Customer already exists by this
	point — see ``create()``), gets its Dynamic Link appended in the *same* save
	as everything else here, instead of a separate reload-and-resave pass."""
	address_input = address_input or {}
	has_input = bool(address_input.get("address_line1"))

	if existing_address:
		addr = frappe.get_doc(ADDRESS, existing_address)
		for fieldname in ADDRESS_INPUT_FIELDS:
			if address_input.get(fieldname):
				addr.set(fieldname, address_input[fieldname])
		addr.update(address_question_fields)
		if org_doc:
			_append_link_if_missing(addr, ORGANIZATION, org_doc.name)
		if linked_customer:
			_append_link_if_missing(addr, CUSTOMER, linked_customer)
		addr.save()
		if org_doc and not org_doc.address:
			frappe.db.set_value(ORGANIZATION, org_doc.name, "address", addr.name)
		return addr.name

	if org_doc and org_doc.address and not has_input:
		if address_question_fields or linked_customer:
			addr = frappe.get_doc(ADDRESS, org_doc.address)
			for fieldname in ADDRESS_INPUT_FIELDS:
				if address_input.get(fieldname):
					addr.set(fieldname, address_input[fieldname])
			addr.update(address_question_fields)
			appended = _append_link_if_missing(addr, CUSTOMER, linked_customer) if linked_customer else False
			if address_question_fields or appended:
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
	addr.address_type = addr.address_type or "Billing"
	if org_doc:
		addr.append("links", {"link_doctype": ORGANIZATION, "link_name": org_doc.name})
	if linked_customer:
		addr.append(
			"links", {"link_doctype": CUSTOMER, "link_name": linked_customer, "link_title": linked_customer}
		)
	addr.insert()

	if org_doc and not org_doc.address:
		frappe.db.set_value(ORGANIZATION, org_doc.name, "address", addr.name)

	return addr.name


def _apply_contact_updates(contact_name: str, contact_fields: dict, *, linked_customer: str | None = None):
	"""Applies resolved question fields and, when given (see ``_upsert_address``'s
	``linked_customer``), appends the Customer Dynamic Link — both in one save."""
	if not contact_fields and not linked_customer:
		return
	contact = frappe.get_doc(CONTACT, contact_name)
	if contact_fields:
		contact.update(contact_fields)
	appended = _append_link_if_missing(contact, CUSTOMER, linked_customer) if linked_customer else False
	if contact_fields or appended:
		contact.save()


def _append_link_if_missing(doc, link_doctype: str, link_name: str) -> bool:
	"""Appends a Dynamic Link row for ``link_doctype``/``link_name`` onto ``doc``'s
	``links`` table, in memory, unless already present. Returns whether it changed
	anything — callers decide whether/when that's worth a save."""
	already_linked = any(row.link_doctype == link_doctype and row.link_name == link_name for row in doc.links)
	if already_linked:
		return False
	doc.append("links", {"link_doctype": link_doctype, "link_name": link_name, "link_title": link_name})
	return True
