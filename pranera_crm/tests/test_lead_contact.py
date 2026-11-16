import unittest
from unittest.mock import patch

import frappe
from crm.tests import CRMTestCase

from pranera_crm import lead_contact

ORG = "ZED LINK TRADERS"
OTHER = "ZED OTHER COMPANY"


def _customer(name):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
				"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
	return name


def _organization(name):
	if not frappe.db.exists("CRM Organization", name):
		frappe.get_doc({"doctype": "CRM Organization", "organization_name": name}).insert(
			ignore_permissions=True
		)
	return name


class TestLeadContact(CRMTestCase):
	# CRMTestCase rolls back after the class, not after each test: each test uses its own names
	numbers = iter(range(9000000100, 9000000200))

	def setUp(self):
		frappe.set_user("Administrator")
		self.mobile = str(next(self.numbers))
		self.contact = (
			frappe.get_doc(
				{
					"doctype": "Contact",
					"first_name": "Zed Link",
					"phone_nos": [{"phone": f"91{self.mobile}", "is_primary_mobile_no": 1}],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def lead(self, organization):
		with patch.object(lead_contact.frappe, "enqueue"):
			lead = frappe.get_doc(
				{
					"doctype": "CRM Lead",
					"first_name": "Zed Link",
					"mobile_no": f"+91-{self.mobile}",
					"email": f"{self.mobile}@noemail.local",
				}
			)
			lead.flags.ignore_mandatory = True
			lead.insert(ignore_permissions=True)
		frappe.db.set_value("CRM Lead", lead.name, "organization", organization)
		return lead.name

	def contact_doc(self):
		return frappe.get_doc("Contact", self.contact)

	def customers(self):
		return {link.link_name for link in self.contact_doc().links if link.link_doctype == "Customer"}

	def test_existing_organization_and_customer(self):
		_organization(ORG)
		_customer(ORG)
		self.assertEqual(lead_contact.link_contact(self.lead(ORG)), [self.contact])
		self.assertEqual(self.contact_doc().company_name, ORG)
		self.assertEqual(self.customers(), {ORG})

	def test_customer_only(self):
		name = _customer("ZED CUSTOMER ONLY")
		lead_contact.link_contact(self.lead(name))
		self.assertFalse(self.contact_doc().company_name)
		self.assertEqual(self.customers(), {name})

	def test_organization_only(self):
		name = _organization("ZED ORGANIZATION ONLY")
		lead_contact.link_contact(self.lead(name))
		self.assertEqual(self.contact_doc().company_name, name)
		self.assertEqual(self.customers(), set())

	@unittest.skipUnless(
		frappe.get_meta("CRM Organization").has_field("custom_customer"),
		"this site's CRM Organization has no Customer field",
	)
	def test_organization_mapped_to_a_customer_of_another_name(self):
		_organization(ORG)
		_customer(OTHER)
		frappe.db.set_value("CRM Organization", ORG, "custom_customer", OTHER)
		lead_contact.link_contact(self.lead(ORG))
		self.assertEqual(self.customers(), {OTHER})

	def test_unknown_name_links_nothing(self):
		self.assertEqual(lead_contact.link_contact(self.lead("ZED NOBODY LTD")), [])
		self.assertFalse(self.contact_doc().company_name)
		self.assertEqual(self.customers(), set())

	def test_contact_under_another_company_keeps_it(self):
		_organization(ORG)
		_customer(ORG)
		frappe.db.set_value("Contact", self.contact, "company_name", OTHER)
		lead_contact.link_contact(self.lead(ORG))
		self.assertEqual(self.contact_doc().company_name, OTHER)
		self.assertEqual(self.customers(), {ORG})

	def test_running_twice_adds_nothing_twice(self):
		_customer(ORG)
		lead = self.lead(ORG)
		lead_contact.link_contact(lead)
		self.assertEqual(lead_contact.link_contact(lead), [])
		self.assertEqual(len(self.contact_doc().links), 1)

	def test_queued_only_when_the_organization_changes(self):
		lead = self.lead(ORG)
		doc = frappe.get_doc("CRM Lead", lead)
		with patch.object(lead_contact.frappe, "enqueue") as enqueue:
			doc.first_name = "Zed Renamed"
			doc.flags.ignore_mandatory = True
			doc.save(ignore_permissions=True)
			enqueue.assert_not_called()
			doc.organization = OTHER
			doc.save(ignore_permissions=True)
			enqueue.assert_called_once()
			self.assertEqual(enqueue.call_args.kwargs["lead"], lead)
