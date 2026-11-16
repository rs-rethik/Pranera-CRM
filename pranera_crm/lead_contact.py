"""A lead's contact joins its organization and customer.

When a CRM Lead's Organization is filled in (at creation, or later by the sales person who has checked
which company the person belongs to) and it names an existing CRM Organization or Customer, the
Contact with the lead's mobile number is put under them:

- an existing CRM Organization of that name → the Contact's Company Name (only when it has none: a
  contact already under another company keeps it);
- the organization's Customer (CRM Organization → Customer), else a Customer of that name → a Customer
  row in the Contact's Links (next to any it has).

A name that matches no existing organization or customer links nothing. The work runs in the
background after the lead is saved, so a contact that can't be saved never blocks the lead.
"""

import re

import frappe

LEAD = "CRM Lead"
ORGANIZATION = "CRM Organization"


def on_lead_change(doc, method=None):
	"""CRM Lead after_insert / on_update: queue the linking when the Organization is new."""
	if not (doc.get("organization") and doc.get("mobile_no")):
		return
	if method == "on_update" and not doc.has_value_changed("organization"):
		return
	frappe.enqueue(
		"pranera_crm.lead_contact.link_contact",
		queue="short",
		enqueue_after_commit=True,
		lead=doc.name,
	)


def link_contact(lead: str) -> list[str]:
	"""Background job: put the lead's contacts under its organization and customer. Returns the
	contacts changed."""
	row = frappe.db.get_value(LEAD, lead, ["organization", "mobile_no"], as_dict=True)
	if not row or not row.organization:
		return []
	organization = frappe.db.exists(ORGANIZATION, row.organization)
	customer = _customer_of(row.organization, organization)
	if not (organization or customer):
		return []
	changed = []
	for name in contacts_with_mobile(row.mobile_no):
		frappe.db.savepoint("lead_contact")
		try:
			if _put_under(name, organization, customer):
				changed.append(name)
		except Exception:
			# a job entry point: one contact that can't be saved is undone and logged, the others go on
			frappe.db.rollback(save_point="lead_contact")
			frappe.log_error(title=f"Pranera CRM: could not link contact {name} to {row.organization}")
	return changed


def _customer_of(organization_name: str, organization: str | None) -> str | None:
	"""The Customer behind an organization: the organization's own Customer link, else a Customer with
	that name or customer name."""
	if organization and frappe.get_meta(ORGANIZATION).has_field("custom_customer"):
		linked = frappe.db.get_value(ORGANIZATION, organization, "custom_customer")
		if linked:
			return linked
	return frappe.db.exists("Customer", organization_name) or frappe.db.get_value(
		"Customer", {"customer_name": organization_name}, "name"
	)


def contacts_with_mobile(mobile: str | None) -> list[str]:
	"""Contacts whose mobile or phone ends in the same 10 digits (+91-…, 91…, spaces and all)."""
	digits = re.sub(r"\D", "", mobile or "")[-10:]
	if len(digits) != 10:
		return []
	pattern = f"%{digits}"
	contact = frappe.qb.DocType("Contact")
	phone = frappe.qb.DocType("Contact Phone")
	by_mobile = (frappe.qb.from_(contact).select(contact.name).where(contact.mobile_no.like(pattern))).run(
		pluck=True
	)
	by_phone = (
		frappe.qb.from_(phone)
		.select(phone.parent)
		.where((phone.parenttype == "Contact") & (phone.phone.like(pattern)))
	).run(pluck=True)
	return list(dict.fromkeys(by_mobile + by_phone))


def _put_under(name: str, organization: str | None, customer: str | None) -> bool:
	contact = frappe.get_doc("Contact", name)
	changed = False
	if organization and not contact.company_name:
		contact.company_name = organization
		changed = True
	if customer and not any(
		link.link_doctype == "Customer" and link.link_name == customer for link in contact.links
	):
		contact.append("links", {"link_doctype": "Customer", "link_name": customer})
		changed = True
	if changed:
		# a system-side update the lead's save asked for, not the user editing the contact
		contact.save(ignore_permissions=True)
	return changed
