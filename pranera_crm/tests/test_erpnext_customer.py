import frappe

from crm.tests import CRMTestCase
from pranera_crm import customer_wizard as cw
from pranera_crm import erpnext_customer as ec
from pranera_crm.api import convert
from pranera_crm.tests.test_api import _hash, deal_status, make_lead, make_org, make_user
from pranera_crm.tests.test_customer_wizard import isolate_from_seed_questions, make_question


def set_erpnext_bridge(enabled):
	frappe.db.set_single_value("ERPNext CRM Settings", "enabled", 1 if enabled else 0)


def make_deal(*, organization=None, contact=None, is_primary=True):
	data = {"doctype": "CRM Deal", "status": deal_status()}
	if organization:
		data["organization"] = organization
	if contact:
		data["contacts"] = [{"contact": contact, "is_primary": 1 if is_primary else 0}]
	return frappe.get_doc(data).insert(ignore_permissions=True)


def make_contact(first_name="Ada", email=None):
	return frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"email_ids": [{"email_id": email or f"ct-{_hash()}@example.com", "is_primary": 1}],
		}
	).insert(ignore_permissions=True)


class TestConvertWithCustomerSetup(CRMTestCase):
	"""End to end through the whitelisted `convert` API."""

	def setUp(self):
		frappe.set_user("Administrator")
		set_erpnext_bridge(True)
		isolate_from_seed_questions()
		self.deal = {"status": deal_status()}

	def tearDown(self):
		frappe.set_user("Administrator")
		set_erpnext_bridge(True)
		frappe.db.rollback()

	def test_setup_customer_false_creates_no_customer(self):
		lead = make_lead()
		response = convert(lead.name, deal=self.deal, setup_customer=False)
		self.assertIsNone(response["customer"])
		self.assertFalse(frappe.db.exists("Customer", {"crm_deal": response["deal"]}))

	def test_disabled_bridge_skips_customer_silently(self):
		set_erpnext_bridge(False)
		lead = make_lead()
		response = convert(lead.name, deal=self.deal, setup_customer=True)
		self.assertIsNotNone(response["deal"])
		self.assertIsNone(response["customer"])
		self.assertIsNone(response["customer_error"])

	def test_full_setup_creates_linked_customer_address_contact(self):
		gst_q = make_question(
			question_key=f"_it_gst_{_hash()}",
			label="Does the customer have a GSTIN?",
			target_doctype="Customer",
			target_fieldname="gst_category",
			options=[
				{"option_label": "No", "option_value": "no", "mapped_value": "Unregistered"},
			],
		)
		group_q = make_question(
			question_key=f"_it_group_{_hash()}",
			label="What kind of customer is this?",
			target_doctype="Customer",
			target_fieldname="customer_group",
			options=[{"option_label": "Commercial", "option_value": "commercial", "mapped_value": "Commercial"}],
		)
		designation_q = make_question(
			question_key=f"_it_designation_{_hash()}",
			label="What is this person's role?",
			scope="Contact",
			target_doctype="Contact",
			target_fieldname="designation",
			options=[{"option_label": "Owner", "option_value": "owner", "mapped_value": "Owner"}],
		)

		lead = make_lead()
		response = convert(
			lead.name,
			deal=self.deal,
			setup_customer=True,
			customer_answers=frappe.as_json({gst_q.question_key: "no", group_q.question_key: "commercial"}),
			contact_customer_answers=frappe.as_json({designation_q.question_key: "owner"}),
			customer_address=frappe.as_json(
				{"address_line1": "1 MG Road", "city": "Chennai", "state": "Tamil Nadu", "country": "India", "pincode": "600001"}
			),
		)

		self.assertIsNone(response["customer_error"])
		self.assertIsNone(response["duplicate_customer"])
		customer = frappe.get_doc("Customer", response["customer"])
		self.assertEqual(customer.gst_category, "Unregistered")
		self.assertEqual(customer.customer_group, "Commercial")
		self.assertEqual(customer.crm_deal, response["deal"])
		self.assertTrue(customer.customer_primary_address)
		self.assertTrue(customer.customer_primary_contact)

		self.assertEqual(frappe.db.get_value("CRM Deal", response["deal"], "erpnext_customer"), customer.name)

		address = frappe.get_doc("Address", customer.customer_primary_address)
		self.assertEqual(address.city, "Chennai")
		self.assertTrue(any(link.link_doctype == "Customer" and link.link_name == customer.name for link in address.links))

		contact = frappe.get_doc("Contact", customer.customer_primary_contact)
		self.assertEqual(contact.designation, "Owner")
		self.assertTrue(any(link.link_doctype == "Customer" and link.link_name == customer.name for link in contact.links))
		# the same Contact created by the Deal step, not a duplicate
		deal_contact = frappe.db.get_value("CRM Deal", response["deal"], "name")
		deal_doc = frappe.get_doc("CRM Deal", deal_contact)
		self.assertEqual([c.contact for c in deal_doc.contacts], [contact.name])

	def test_gst_validation_failure_does_not_lose_the_deal(self):
		lead = make_lead()
		response = convert(
			lead.name,
			deal=self.deal,
			setup_customer=True,
			customer_address=frappe.as_json({"address_line1": "1 MG Road", "city": "Chennai", "state": "Tamil Nadu", "country": "India", "gstin": "NOT-A-GSTIN"}),
		)
		self.assertIsNotNone(response["deal"])
		self.assertIsNone(response["customer"])
		self.assertTrue(response["customer_error"])

		# the deal itself is genuinely converted, not just returned in the response
		lead.reload()
		self.assertTrue(lead.converted)
		self.assertFalse(frappe.db.exists("Customer", {"crm_deal": response["deal"]}))

	def test_override_by_permitted_role(self):
		q = make_question(
			target_doctype="Customer",
			target_fieldname="customer_group",
			options=[{"option_label": "Commercial", "option_value": "commercial", "mapped_value": "Commercial"}],
			override_roles="Sales Manager",
		)
		user = make_user(roles=["Sales User", "Sales Manager"])
		frappe.set_user(user)
		lead = make_lead(lead_owner=user)
		response = convert(
			lead.name,
			deal=self.deal,
			setup_customer=True,
			customer_answers=frappe.as_json({q.question_key: "commercial"}),
			customer_overrides=frappe.as_json({q.question_key: "Individual"}),
		)
		customer = frappe.get_doc("Customer", response["customer"])
		self.assertEqual(customer.customer_group, "Individual")


class TestErpnextCustomerCreate(CRMTestCase):
	"""Direct tests against erpnext_customer.create(), for cases that need to call it
	more than once against the same Deal (convert() only allows one conversion per lead)."""

	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_reuses_organizations_existing_address(self):
		org = make_org()
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": org.name,
				"address_type": "Billing",
				"address_line1": "Old Address",
				"city": "Chennai",
				"state": "Tamil Nadu",
				"country": "India",
				"links": [{"link_doctype": "CRM Organization", "link_name": org.name}],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("CRM Organization", org.name, "address", address.name)

		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		self.assertEqual(frappe.get_doc("Customer", result["customer"]).customer_primary_address, address.name)
		self.assertEqual(frappe.db.count("Address", {"address_title": org.name}), 1)  # no duplicate created

	def test_creates_address_when_organization_has_none(self):
		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(
			deal=deal.name,
			organization_answers={},
			contact_answers={},
			address={"address_line1": "1 MG Road", "city": "Chennai", "state": "Tamil Nadu", "country": "India"},
		)
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertTrue(customer.customer_primary_address)
		self.assertEqual(frappe.db.get_value("CRM Organization", org.name, "address"), customer.customer_primary_address)

	def test_no_address_input_and_no_existing_address_skips_address(self):
		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertFalse(customer.customer_primary_address)

	def test_duplicate_customer_name_requires_confirmation(self):
		org = make_org()
		existing = frappe.get_doc({"doctype": "Customer", "customer_name": org.name}).insert(ignore_permissions=True)
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		with self.assertRaises(ec.DuplicateCustomerName) as ctx:
			ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		self.assertEqual(ctx.exception.existing_customer, existing.name)
		self.assertEqual(frappe.db.count("Customer", {"customer_name": org.name}), 1)

		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={}, confirm_duplicate=True)
		self.assertEqual(result["customer"], existing.name)
		self.assertEqual(frappe.db.count("Customer", {"customer_name": org.name}), 1)  # still just the one

	def test_sales_person_resolves_into_sales_team_row(self):
		sp = frappe.get_doc(
			{"doctype": "Sales Person", "sales_person_name": f"Test SP {_hash()}", "enabled": 1, "is_group": 0}
		).insert(ignore_permissions=True)
		q = make_question(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			source_doctype="Sales Person",
			source_label_field="sales_person_name",
			source_filters='{"enabled": 1, "is_group": 0}',
		)
		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(
			deal=deal.name, organization_answers={q.question_key: sp.name}, contact_answers={}, address={}
		)
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertEqual([row.sales_person for row in customer.sales_team], [sp.name])

	def test_reuses_the_deals_existing_contact_not_a_duplicate(self):
		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertEqual(customer.customer_primary_contact, contact.name)
		self.assertEqual(frappe.db.count("Contact", {"first_name": contact.first_name}), 1)

	def test_no_organization_falls_back_to_primary_contact_name(self):
		contact = make_contact(first_name="Solo")
		deal = make_deal(contact=contact.name)
		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertIn("Solo", customer.customer_name)

	def test_permission_denied_without_customer_create_role(self):
		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		# Accounts User has read-only access to Customer in ERPNext core (no Sales
		# User/Sales Master Manager role), so create() must still fail via the
		# ordinary Document.insert() permission check.
		user = make_user(roles=["Accounts User"], prefix="cw-noperm")
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
