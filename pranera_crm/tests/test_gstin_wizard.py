from unittest.mock import patch

import frappe
from crm.tests import CRMTestCase

from pranera_crm import erpnext_customer as ec
from pranera_crm.api import convert, find_candidates
from pranera_crm.tests.test_api import _hash, deal_status, make_lead

# valid in shape only; set straight in the database so no GST check runs on it
GSTIN = "33AAACZ1234Q1Z5"


def make_customer(name=None, gstin=None):
	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": name or f"GSTIN Customer {_hash()}",
			"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
			"territory": frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		}
	).insert(ignore_permissions=True)
	if gstin and customer.meta.has_field("gstin"):
		frappe.db.set_value("Customer", customer.name, "gstin", gstin)
	return customer.name


class TestCheckGstin(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_existing_customer_is_found_and_the_portal_not_asked(self):
		gstin = GSTIN
		customer = make_customer(gstin=gstin)
		with patch.object(ec, "lookup_gstin") as portal:
			result = ec.check_gstin(gstin.lower())
			portal.assert_not_called()
		self.assertEqual(result["gstin"], gstin)
		self.assertIn(customer, [c["customer"] for c in result["existing"]])
		self.assertIsNone(result["registered"])

	def test_new_gstin_comes_from_the_portal(self):
		info = {"business_name": "NEW TEXTILES", "address": {"city": "Tiruppur"}, "status": "Active"}
		with patch.object(ec, "lookup_gstin", return_value=info):
			result = ec.check_gstin("33ZZZZZ9999Z1Z9")
		self.assertEqual(result["existing"], [])
		self.assertEqual(result["registered"], info)

	def test_rejects_a_malformed_gstin(self):
		with self.assertRaises(frappe.ValidationError):
			ec.check_gstin("NOT-A-GSTIN")

	def test_summary_shows_addresses_and_contacts(self):
		customer = make_customer()
		frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Summary Person",
				"links": [{"link_doctype": "Customer", "link_name": customer}],
			}
		).insert(ignore_permissions=True)
		summary = ec.customer_summary(customer)
		self.assertEqual(summary["customer"], customer)
		self.assertEqual([c["full_name"] for c in summary["contacts"]], ["Summary Person"])
		self.assertEqual(summary["addresses"], [])


class TestConvertForExistingCustomer(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.deal = {"status": deal_status()}

	def test_links_the_existing_customer_and_creates_no_customer(self):
		customer = make_customer()
		lead = make_lead()
		before = frappe.db.count("Customer")
		result = convert(lead.name, deal=self.deal, existing_customer=customer, setup_customer=True)
		self.assertEqual(frappe.db.count("Customer"), before)
		self.assertEqual(result["customer"], customer)
		deal = frappe.get_doc("CRM Deal", result["deal"])
		# the deal sits under the customer's CRM Organization, made from the customer name
		self.assertEqual(deal.organization, ec.organization_of_customer(customer))
		self.assertEqual(
			frappe.db.get_value("CRM Organization", deal.organization, "organization_name"),
			frappe.db.get_value("Customer", customer, "customer_name"),
		)
		if deal.meta.has_field("erpnext_customer"):
			self.assertEqual(frappe.db.get_value("CRM Deal", deal.name, "erpnext_customer"), customer)
		for row in deal.contacts:
			links = frappe.get_all(
				"Dynamic Link",
				filters={"parenttype": "Contact", "parent": row.contact, "link_doctype": "Customer"},
				pluck="link_name",
			)
			self.assertIn(customer, links)

	def test_uses_the_customers_own_organization(self):
		customer = make_customer()
		name = frappe.db.get_value("Customer", customer, "customer_name")
		org = frappe.get_doc({"doctype": "CRM Organization", "organization_name": name}).insert()
		lead = make_lead()
		result = convert(lead.name, deal=self.deal, existing_customer=customer)
		self.assertEqual(frappe.db.get_value("CRM Deal", result["deal"], "organization"), org.name)

	def test_unknown_customer_is_refused(self):
		lead = make_lead()
		with self.assertRaises(frappe.DoesNotExistError):
			convert(lead.name, deal=self.deal, existing_customer="NO SUCH CUSTOMER")


class TestCustomersForLead(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def test_finds_the_customer_by_the_leads_mobile_and_by_name(self):
		by_mobile = make_customer()
		digits = f"8{int(_hash()[:6], 16) % 10**9:09d}"
		frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Lead Person",
				"phone_nos": [{"phone": f"91{digits}", "is_primary_mobile_no": 1}],
				"links": [{"link_doctype": "Customer", "link_name": by_mobile}],
			}
		).insert(ignore_permissions=True)
		by_name = make_customer()
		lead = make_lead(
			mobile_no=f"+91-{digits}",
			organization=frappe.db.get_value("Customer", by_name, "customer_name"),
		)
		found = {c["customer"]: c["matched_by"] for c in ec.customers_for_lead(lead.name)}
		self.assertEqual(found, {by_mobile: "mobile", by_name: "name"})

	def test_nothing_for_a_new_person(self):
		lead = make_lead(organization=f"Nobody Yet {_hash()}")
		self.assertEqual(ec.customers_for_lead(lead.name), [])


class TestContactMatchByNumber(CRMTestCase):
	def test_gate_contact_is_found_for_the_leads_mobile(self):
		frappe.set_user("Administrator")
		digits = f"9{int(_hash()[:6], 16) % 10**9:09d}"
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Gate Person",
				"phone_nos": [{"phone": f"91{digits}", "is_primary_mobile_no": 1}],
			}
		).insert(ignore_permissions=True)
		result = find_candidates(mobile_no=f"+91-{digits}")
		self.assertIn(contact.name, [c["name"] for c in result["contacts"]])
		self.assertEqual(result["auto_contact"], contact.name)
