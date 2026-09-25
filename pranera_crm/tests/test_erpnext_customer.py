from typing import ClassVar

import frappe
from crm.tests import CRMTestCase

from pranera_crm import customer_wizard as cw
from pranera_crm import erpnext_customer as ec
from pranera_crm.api import convert, get_wizard_context, setup_customer_for_deal
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

	def test_resolve_runs_once_per_scope_not_twice(self):
		"""P1: a full convert(setup_customer=True) with a new org/contact used to
		call cw.resolve() twice per scope (once for the Lead prefill, once again
		inside erpnext_customer.create()) — api.convert() now resolves each scope
		once and passes the result through."""
		from unittest.mock import patch

		lead = make_lead()
		with patch("pranera_crm.customer_wizard.resolve", wraps=cw.resolve) as spy:
			response = convert(lead.name, deal=self.deal, setup_customer=True)
		self.assertTrue(response["customer"])
		scopes = [c.args[0] for c in spy.call_args_list]
		self.assertEqual(scopes.count("Organization"), 1)
		self.assertEqual(scopes.count("Contact"), 1)

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
			options=[
				{"option_label": "Commercial", "option_value": "commercial", "mapped_value": "Commercial"}
			],
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
				{
					"address_line1": "1 MG Road",
					"city": "Chennai",
					"state": "Tamil Nadu",
					"country": "India",
					"pincode": "600001",
				}
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
		self.assertTrue(
			any(link.link_doctype == "Customer" and link.link_name == customer.name for link in address.links)
		)

		contact = frappe.get_doc("Contact", customer.customer_primary_contact)
		self.assertEqual(contact.designation, "Owner")
		self.assertTrue(
			any(link.link_doctype == "Customer" and link.link_name == customer.name for link in contact.links)
		)
		deal_contact = frappe.db.get_value("CRM Deal", response["deal"], "name")
		deal_doc = frappe.get_doc("CRM Deal", deal_contact)
		self.assertEqual([c.contact for c in deal_doc.contacts], [contact.name])

	def test_customer_existing_address_end_to_end(self):
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": f"Reused Address {_hash()}",
				"address_type": "Billing",
				"address_line1": "10 Reused Road",
				"city": "Chennai",
				"state": "Tamil Nadu",
				"country": "India",
			}
		).insert(ignore_permissions=True)
		lead = make_lead()

		response = convert(
			lead.name,
			deal=self.deal,
			setup_customer=True,
			customer_existing_address=address.name,
		)

		self.assertIsNone(response["customer_error"])
		customer = frappe.get_doc("Customer", response["customer"])
		self.assertEqual(customer.customer_primary_address, address.name)

	def test_unknown_customer_existing_address_rejected(self):
		lead = make_lead()
		with self.assertRaises(frappe.DoesNotExistError):
			convert(
				lead.name,
				deal=self.deal,
				setup_customer=True,
				customer_existing_address="No Such Address",
			)

	def test_gst_validation_failure_does_not_lose_the_deal(self):
		lead = make_lead()
		response = convert(
			lead.name,
			deal=self.deal,
			setup_customer=True,
			customer_address=frappe.as_json(
				{
					"address_line1": "1 MG Road",
					"city": "Chennai",
					"state": "Tamil Nadu",
					"country": "India",
					"gstin": "NOT-A-GSTIN",
				}
			),
		)
		self.assertIsNotNone(response["deal"])
		self.assertIsNone(response["customer"])
		self.assertTrue(response["customer_error"])

		lead.reload()
		self.assertTrue(lead.converted)
		self.assertFalse(frappe.db.exists("Customer", {"crm_deal": response["deal"]}))

	def test_override_by_permitted_role(self):
		q = make_question(
			target_doctype="Customer",
			target_fieldname="customer_group",
			options=[
				{"option_label": "Commercial", "option_value": "commercial", "mapped_value": "Commercial"}
			],
			override_roles=[{"role": "Sales Manager"}],
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
		self.assertEqual(
			frappe.get_doc("Customer", result["customer"]).customer_primary_address, address.name
		)
		self.assertEqual(frappe.db.count("Address", {"address_title": org.name}), 1)

	def test_typing_a_new_address_creates_a_second_one_instead_of_overwriting(self):
		"""Even though the Organization already has an Address, manually typed
		input must never silently mutate it — that Address could be linked to, or
		shared with, other parties. Only an explicit `existing_address` pick may
		edit an already-linked Address."""
		org = make_org()
		old_address = frappe.get_doc(
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
		frappe.db.set_value("CRM Organization", org.name, "address", old_address.name)

		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(
			deal=deal.name,
			organization_answers={},
			contact_answers={},
			address={
				"address_line1": "Brand New Street",
				"city": "Bengaluru",
				"state": "Karnataka",
				"country": "India",
			},
		)

		customer = frappe.get_doc("Customer", result["customer"])
		self.assertNotEqual(customer.customer_primary_address, old_address.name)
		new_address = frappe.get_doc("Address", customer.customer_primary_address)
		self.assertEqual(new_address.address_line1, "Brand New Street")
		old_address.reload()
		self.assertEqual(old_address.address_line1, "Old Address")
		self.assertEqual(frappe.db.get_value("CRM Organization", org.name, "address"), old_address.name)

	def test_creates_address_when_organization_has_none(self):
		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(
			deal=deal.name,
			organization_answers={},
			contact_answers={},
			address={
				"address_line1": "1 MG Road",
				"city": "Chennai",
				"state": "Tamil Nadu",
				"country": "India",
			},
		)
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertTrue(customer.customer_primary_address)
		self.assertEqual(
			frappe.db.get_value("CRM Organization", org.name, "address"), customer.customer_primary_address
		)

	def test_no_address_input_and_no_existing_address_skips_address(self):
		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertFalse(customer.customer_primary_address)

	def test_existing_address_is_reused_not_recreated(self):
		address_type_q = make_question(
			target_doctype="Address",
			target_fieldname="address_type",
			options=[{"option_label": "Office", "option_value": "office", "mapped_value": "Office"}],
		)
		org = make_org()
		other = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": f"Some Other Party {_hash()}",
				"address_type": "Billing",
				"address_line1": "42 Elsewhere Street",
				"city": "Chennai",
				"state": "Tamil Nadu",
				"country": "India",
			}
		).insert(ignore_permissions=True)
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)
		addresses = frappe.db.count("Address")

		result = ec.create(
			deal=deal.name,
			organization_answers={address_type_q.question_key: "office"},
			contact_answers={},
			address={},
			existing_address=other.name,
		)

		self.assertEqual(frappe.db.count("Address"), addresses)
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertEqual(customer.customer_primary_address, other.name)
		other.reload()
		self.assertEqual(other.address_type, "Office")
		self.assertTrue(
			any(row.link_doctype == "CRM Organization" and row.link_name == org.name for row in other.links)
		)
		self.assertEqual(frappe.db.get_value("CRM Organization", org.name, "address"), other.name)

	def test_contact_saved_once(self):
		"""P2: field updates and the Customer Dynamic Link append must land in the
		same save, not two round trips."""
		from unittest.mock import patch

		from frappe.model.document import Document

		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)
		q = make_question(
			scope="Contact",
			target_doctype="Contact",
			target_fieldname="designation",
			options=[{"option_label": "Manager", "option_value": "manager", "mapped_value": "Manager"}],
		)

		saves = []
		original_save = Document.save

		def counting_save(self, *args, **kwargs):
			if self.doctype == "Contact" and self.name == contact.name:
				saves.append(1)
			return original_save(self, *args, **kwargs)

		with patch.object(Document, "save", counting_save):
			ec.create(
				deal=deal.name,
				organization_answers={},
				contact_answers={q.question_key: "manager"},
				address={},
			)

		self.assertEqual(len(saves), 1)
		contact.reload()
		self.assertEqual(contact.designation, "Manager")
		self.assertTrue(any(row.link_doctype == "Customer" for row in contact.links))

	def test_address_inserted_once_when_freshly_created(self):
		from unittest.mock import patch

		from frappe.model.document import Document

		org = make_org()
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		inserts, saves = [], []
		original_insert, original_save = Document.insert, Document.save

		def counting_insert(self, *args, **kwargs):
			if self.doctype == "Address":
				inserts.append(1)
			return original_insert(self, *args, **kwargs)

		def counting_save(self, *args, **kwargs):
			if self.doctype == "Address":
				saves.append(1)
			return original_save(self, *args, **kwargs)

		with patch.object(Document, "insert", counting_insert), patch.object(Document, "save", counting_save):
			result = ec.create(
				deal=deal.name,
				organization_answers={},
				contact_answers={},
				address={
					"address_line1": "1 MG Road",
					"city": "Chennai",
					"state": "Tamil Nadu",
					"country": "India",
				},
			)

		self.assertEqual(inserts, [1])
		self.assertEqual(saves, [])
		address = frappe.get_doc(
			"Address", frappe.get_doc("Customer", result["customer"]).customer_primary_address
		)
		self.assertTrue(any(row.link_doctype == "Customer" for row in address.links))
		self.assertTrue(any(row.link_doctype == "CRM Organization" for row in address.links))

	def test_address_saved_once_when_reusing_via_existing_address(self):
		from unittest.mock import patch

		from frappe.model.document import Document

		org = make_org()
		other = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": f"Some Other Party {_hash()}",
				"address_type": "Billing",
				"address_line1": "42 Elsewhere Street",
				"city": "Chennai",
				"state": "Tamil Nadu",
				"country": "India",
			}
		).insert(ignore_permissions=True)
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		saves = []
		original_save = Document.save

		def counting_save(self, *args, **kwargs):
			if self.doctype == "Address" and self.name == other.name:
				saves.append(1)
			return original_save(self, *args, **kwargs)

		with patch.object(Document, "save", counting_save):
			ec.create(
				deal=deal.name,
				organization_answers={},
				contact_answers={},
				address={},
				existing_address=other.name,
			)

		self.assertEqual(len(saves), 1)
		other.reload()
		self.assertTrue(any(row.link_doctype == "Customer" for row in other.links))
		self.assertTrue(any(row.link_doctype == "CRM Organization" for row in other.links))

	def test_duplicate_customer_name_requires_confirmation(self):
		org = make_org()
		existing = frappe.get_doc({"doctype": "Customer", "customer_name": org.name}).insert(
			ignore_permissions=True
		)
		contact = make_contact()
		deal = make_deal(organization=org.name, contact=contact.name)

		with self.assertRaises(ec.DuplicateCustomerName) as ctx:
			ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		self.assertEqual(ctx.exception.existing_customer, existing.name)
		self.assertEqual(frappe.db.count("Customer", {"customer_name": org.name}), 1)

		result = ec.create(
			deal=deal.name, organization_answers={}, contact_answers={}, address={}, confirm_duplicate=True
		)
		self.assertEqual(result["customer"], existing.name)
		self.assertEqual(frappe.db.count("Customer", {"customer_name": org.name}), 1)

	def test_sales_person_resolves_into_sales_team_row(self):
		sp = frappe.get_doc(
			{
				"doctype": "Sales Person",
				"sales_person_name": f"Test SP {_hash()}",
				"enabled": 1,
				"is_group": 0,
			}
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

		user = make_user(roles=["Accounts User"], prefix="cw-noperm")
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})

	def test_gstin_already_used_by_another_customer_is_blocked(self):
		gstin = "27AAPFU0939F1ZV"
		holder = frappe.get_doc({"doctype": "Customer", "customer_name": f"GSTIN Holder {_hash()}"}).insert()
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": holder.customer_name,
				"address_type": "Billing",
				"address_line1": "9 Old Street",
				"city": "Mumbai",
				"country": "India",
				"state": "Maharashtra",
				"gstin": gstin,
				"links": [{"link_doctype": "Customer", "link_name": holder.name}],
			}
		).insert()

		deal = make_deal(organization=make_org().name, contact=make_contact().name)
		with self.assertRaises(frappe.ValidationError) as raised:
			ec.create(
				deal=deal.name,
				organization_answers={},
				contact_answers={},
				address={
					"address_line1": "1 MG Road",
					"city": "Mumbai",
					"state": "Maharashtra",
					"country": "India",
					"gstin": gstin,
				},
			)
		self.assertIn(holder.name, str(raised.exception))

	def test_new_customer_created_disabled(self):
		deal = make_deal(organization=make_org().name, contact=make_contact().name)
		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertEqual(customer.disabled, 1)

	def test_reusing_an_existing_customer_does_not_disable_it(self):
		org = make_org()
		existing = frappe.get_doc({"doctype": "Customer", "customer_name": org.name, "disabled": 0}).insert(
			ignore_permissions=True
		)
		deal = make_deal(organization=org.name, contact=make_contact().name)

		result = ec.create(
			deal=deal.name, organization_answers={}, contact_answers={}, address={}, confirm_duplicate=True
		)
		self.assertEqual(result["customer"], existing.name)
		existing.reload()
		self.assertEqual(existing.disabled, 0)

	def test_sales_person_auto_assigned_from_session_user(self):
		"""'Who handles this customer?' is never asked — it's whoever converts,
		found via User -> Employee.user_id -> Sales Person.employee."""
		user = make_user(roles=["Sales User"], prefix="cw-sp")
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "CW SP",
				"user_id": user,
				"company": frappe.db.get_single_value("Global Defaults", "default_company")
				or frappe.get_all("Company", pluck="name", limit=1)[0],
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"gender": "Prefer not to say" if frappe.db.exists("Gender", "Prefer not to say") else None,
			}
		).insert(ignore_permissions=True)
		sp = frappe.get_doc(
			{
				"doctype": "Sales Person",
				"sales_person_name": f"CW SP {_hash()}",
				"employee": employee.name,
				"enabled": 1,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)

		org = make_org()
		deal = make_deal(organization=org.name, contact=make_contact().name)
		frappe.set_user(user)
		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertEqual([row.sales_person for row in customer.sales_team], [sp.name])

	def test_no_sales_person_assigned_when_user_has_none_linked(self):
		deal = make_deal(organization=make_org().name, contact=make_contact().name)
		result = ec.create(deal=deal.name, organization_answers={}, contact_answers={}, address={})
		customer = frappe.get_doc("Customer", result["customer"])
		self.assertEqual(customer.sales_team, [])

	def test_two_new_sales_persons_split_100_percent_instead_of_each_getting_100(self):
		"""F10: a question-resolved Sales Person and the auto session one both
		landing on a fresh Customer at once must not each get allocated 100%."""
		user = make_user(roles=["Sales User"], prefix="cw-sp-split")
		employee = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "CW Split",
				"user_id": user,
				"company": frappe.db.get_single_value("Global Defaults", "default_company")
				or frappe.get_all("Company", pluck="name", limit=1)[0],
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"gender": "Prefer not to say" if frappe.db.exists("Gender", "Prefer not to say") else None,
			}
		).insert(ignore_permissions=True)
		auto_sp = frappe.get_doc(
			{
				"doctype": "Sales Person",
				"sales_person_name": f"CW Auto {_hash()}",
				"employee": employee.name,
				"enabled": 1,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		question_sp = frappe.get_doc(
			{
				"doctype": "Sales Person",
				"sales_person_name": f"CW Question {_hash()}",
				"enabled": 1,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		q = make_question(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			source_doctype="Sales Person",
			source_label_field="sales_person_name",
		)

		org = make_org()
		deal = make_deal(organization=org.name, contact=make_contact().name)
		frappe.set_user(user)
		result = ec.create(
			deal=deal.name,
			organization_answers={q.question_key: question_sp.name},
			contact_answers={},
			address={},
		)
		customer = frappe.get_doc("Customer", result["customer"])
		rows = {row.sales_person: row.allocated_percentage for row in customer.sales_team}
		self.assertEqual(set(rows), {auto_sp.name, question_sp.name})
		self.assertEqual(sum(rows.values()), 100)
		self.assertEqual(set(rows.values()), {50})

	def test_existing_manual_allocation_is_left_alone_when_a_new_row_is_added(self):
		"""Only the rows THIS call adds are split against each other — an admin's
		own pre-existing allocation on the Customer is never rebalanced away from
		underneath them. ERPNext's own Customer.validate() requires every row to
		sum to exactly 100 on every save, so an existing manual row is always
		already at (its share of) 100 — the new row must split whatever's left
		(here, nothing) rather than a fresh 100, or the save would blow past 100."""
		org = make_org()
		manual_sp = frappe.get_doc(
			{
				"doctype": "Sales Person",
				"sales_person_name": f"CW Manual {_hash()}",
				"enabled": 1,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		new_sp = frappe.get_doc(
			{"doctype": "Sales Person", "sales_person_name": f"CW New {_hash()}", "enabled": 1, "is_group": 0}
		).insert(ignore_permissions=True)
		existing_customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": org.name,
				"sales_team": [{"sales_person": manual_sp.name, "allocated_percentage": 100}],
			}
		).insert(ignore_permissions=True)
		deal = make_deal(organization=org.name, contact=make_contact().name)
		q = make_question(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			source_doctype="Sales Person",
			source_label_field="sales_person_name",
		)

		result = ec.create(
			deal=deal.name,
			organization_answers={q.question_key: new_sp.name},
			contact_answers={},
			address={},
			confirm_duplicate=True,
		)
		self.assertEqual(result["customer"], existing_customer.name)
		customer = frappe.get_doc("Customer", existing_customer.name)
		rows = {row.sales_person: row.allocated_percentage for row in customer.sales_team}
		self.assertEqual(rows, {manual_sp.name: 100, new_sp.name: 0})


class TestSetupCustomerForDeal(CRMTestCase):
	"""The standalone retry/confirm endpoint used after `convert` reports
	`duplicate_customer` or `customer_error` — never touches the Deal/Lead."""

	def setUp(self):
		frappe.set_user("Administrator")
		set_erpnext_bridge(True)
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		set_erpnext_bridge(True)
		frappe.db.rollback()

	def test_retry_after_duplicate_links_to_existing_without_reconverting(self):
		lead = make_lead()
		existing = frappe.get_doc({"doctype": "Customer", "customer_name": lead.organization}).insert(
			ignore_permissions=True
		)

		response = convert(lead.name, deal={"status": deal_status()}, setup_customer=True)
		self.assertEqual(response["duplicate_customer"], existing.name)
		self.assertIsNone(response["customer"])

		retry = setup_customer_for_deal(response["deal"], confirm_duplicate_customer=True)
		self.assertEqual(retry["customer"], existing.name)
		self.assertIsNone(retry["customer_error"])
		self.assertEqual(frappe.db.count("Customer", {"customer_name": lead.organization}), 1)

		lead.reload()
		self.assertTrue(lead.converted)
		self.assertEqual(frappe.db.get_value("CRM Deal", response["deal"], "erpnext_customer"), existing.name)

	def test_retry_after_gst_error_succeeds_with_fixed_answers(self):
		lead = make_lead()
		response = convert(
			lead.name,
			deal={"status": deal_status()},
			setup_customer=True,
			customer_address=frappe.as_json(
				{"address_line1": "1 MG Road", "city": "Chennai", "country": "India", "gstin": "bad"}
			),
		)
		self.assertTrue(response["customer_error"])
		self.assertIsNone(response["customer"])

		retry = setup_customer_for_deal(
			response["deal"],
			customer_address=frappe.as_json(
				{"address_line1": "1 MG Road", "city": "Chennai", "state": "Tamil Nadu", "country": "India"}
			),
		)
		self.assertIsNone(retry["customer_error"])
		self.assertTrue(retry["customer"])

	def test_idempotent_once_customer_already_linked(self):
		lead = make_lead()
		response = convert(lead.name, deal={"status": deal_status()}, setup_customer=True)
		self.assertTrue(response["customer"])
		customers_before = frappe.db.count("Customer")

		retry = setup_customer_for_deal(response["deal"])
		self.assertEqual(retry["customer"], response["customer"])
		self.assertEqual(frappe.db.count("Customer"), customers_before)

	def test_reads_the_linked_customer_field_under_a_row_lock(self):
		"""F3: two concurrent retries (two tabs, a double click past the UI's own
		guard) must not both see "nothing set yet" and both create a Customer —
		guarded by reading `erpnext_customer` with `for_update=True`, the same
		pattern `convert()` already uses for its own read of the Lead."""
		from unittest.mock import patch

		lead = make_lead()
		response = convert(lead.name, deal={"status": deal_status()}, setup_customer=False)

		with patch("frappe.db.get_value", wraps=frappe.db.get_value) as spy:
			setup_customer_for_deal(response["deal"])
		locked_calls = [c for c in spy.call_args_list if c.args[:2] == ("CRM Deal", response["deal"])]
		self.assertTrue(locked_calls)
		self.assertTrue(any(c.kwargs.get("for_update") for c in locked_calls))

	def test_permission_denied_without_deal_write_access(self):
		lead = make_lead()
		response = convert(lead.name, deal={"status": deal_status()}, setup_customer=False)

		user = make_user(roles=[], prefix="cw-deal-noperm")
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			setup_customer_for_deal(response["deal"])

	def test_disabled_bridge_rejected(self):
		lead = make_lead()
		response = convert(lead.name, deal={"status": deal_status()}, setup_customer=False)
		set_erpnext_bridge(False)
		with self.assertRaises(frappe.ValidationError):
			setup_customer_for_deal(response["deal"])

	def test_works_even_when_the_wizard_toggle_is_off(self):
		"""E7: deliberately gated only by the ERPNext bridge, not is_wizard_enabled()
		— "finish what you started" even if an admin disables the wizard mid-flight,
		unlike every other wizard endpoint. Pins that intentional asymmetry."""
		from pranera_crm.settings import ENABLE_FIELD, SETTINGS

		lead = make_lead()
		response = convert(lead.name, deal={"status": deal_status()}, setup_customer=False)

		frappe.db.set_single_value(SETTINGS, ENABLE_FIELD, 0)
		retry = setup_customer_for_deal(response["deal"])
		self.assertIsNone(retry["customer_error"])
		self.assertTrue(retry["customer"])


class TestLookupGstin(CRMTestCase):
	_used_gstins: ClassVar[list] = []

	def setUp(self):
		frappe.set_user("Administrator")
		self._used_gstins = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for gstin in self._used_gstins:
			frappe.cache.delete_value(ec.GSTIN_LOOKUP_CACHE_PREFIX + gstin)
		frappe.db.rollback()

	def _lookup(self, gstin):
		self._used_gstins.append(gstin)
		return ec.lookup_gstin(gstin)

	def test_maps_gstin_info_into_business_name_and_address(self):
		from unittest.mock import patch

		fake_response = frappe._dict(
			{
				"business_name": "Acme Traders",
				"gst_category": "Registered Regular",
				"status": "Active",
				"permanent_address": {
					"address_line1": "1 MG Road",
					"address_line2": "",
					"city": "Chennai",
					"state": "Tamil Nadu",
					"pincode": "600001",
					"country": "India",
				},
			}
		)
		with patch(
			"india_compliance.gst_india.utils.gstin_info.get_gstin_info", return_value=fake_response
		) as mocked:
			result = self._lookup("33AAFCA7488L1Z0")

		mocked.assert_called_once_with("33AAFCA7488L1Z0", throw_error=True)
		self.assertEqual(result["business_name"], "Acme Traders")
		self.assertEqual(result["gst_category"], "Registered Regular")
		self.assertEqual(result["address"]["city"], "Chennai")
		self.assertEqual(result["address"]["state"], "Tamil Nadu")

	def test_missing_permanent_address_returns_blank_address(self):
		from unittest.mock import patch

		fake_response = frappe._dict({"business_name": "Solo Trader", "gst_category": "Unregistered"})
		with patch("india_compliance.gst_india.utils.gstin_info.get_gstin_info", return_value=fake_response):
			result = self._lookup("27AAAFU0939F1ZV")

		self.assertEqual(result["business_name"], "Solo Trader")
		self.assertEqual(
			result["address"],
			{
				k: ("India" if k == "country" else "")
				for k in ["address_line1", "address_line2", "city", "state", "pincode", "country"]
			},
		)

	def test_permission_denied_without_customer_read(self):
		user = make_user(roles=[], prefix="cw-gstin-noperm")
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			self._lookup("29AABCT1332L1ZU")

	def test_second_lookup_of_same_gstin_is_served_from_cache(self):
		"""S3: a GSTIN's registered business data doesn't change minute to minute —
		a repeat lookup must not hit the external API again."""
		from unittest.mock import patch

		fake_response = frappe._dict(
			{"business_name": "Cached Traders", "gst_category": "Registered Regular"}
		)
		with patch(
			"india_compliance.gst_india.utils.gstin_info.get_gstin_info", return_value=fake_response
		) as mocked:
			first = self._lookup("19AABCU9603R1ZM")
			second = self._lookup("19AABCU9603R1ZM")

		mocked.assert_called_once()
		self.assertEqual(first, second)


class TestWizardContextIncludesAllQuestions(CRMTestCase):
	"""Regression test: get_wizard_context must send every enabled question, not just
	the ones visible with an empty answer set — otherwise a follow-up question (e.g.
	"Regular or Composition?") can never be revealed client-side once its parent is
	answered, because the client only branches over what it was given."""

	def setUp(self):
		frappe.set_user("Administrator")
		set_erpnext_bridge(True)
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		set_erpnext_bridge(True)
		frappe.db.rollback()

	def test_conditional_follow_up_question_is_included_up_front(self):
		parent = make_question(
			question_key=f"_ctx_parent_{_hash()}",
			options=[
				{"option_label": "Yes", "option_value": "yes"},
				{"option_label": "No", "option_value": "no", "mapped_value": "Unregistered"},
			],
		)
		child = make_question(
			question_key=f"_ctx_child_{_hash()}",
			depends_on_question=parent.name,
			depends_on_option="yes",
			options=[
				{"option_label": "Regular", "option_value": "regular", "mapped_value": "Registered Regular"}
			],
		)

		lead = make_lead()
		ctx = get_wizard_context(lead.name)
		keys = [q["question_key"] for q in ctx["customer"]["organization_questions"]]
		self.assertIn(parent.question_key, keys)
		self.assertIn(child.question_key, keys)

		child_payload = next(
			q for q in ctx["customer"]["organization_questions"] if q["question_key"] == child.question_key
		)
		self.assertEqual(child_payload["depends_on_question"], parent.name)
		self.assertEqual(child_payload["depends_on_option"], "yes")


class TestValidateResolvedFields(CRMTestCase):
	def test_link_values_are_checked_with_one_query_per_linked_doctype(self):
		from unittest.mock import patch

		fields = {
			"Customer": {"territory": "India", "customer_group": "Commercial", "default_currency": "INR"},
			"Address": {"gst_category": "Unregistered"},
		}
		with (
			patch("frappe.get_all", wraps=frappe.get_all) as spy,
			patch("frappe.db.exists", wraps=frappe.db.exists) as exists,
		):
			ec._validate_resolved_fields(fields)

		linked = [c.args[0] for c in spy.call_args_list]
		for link_doctype in ("Currency", "Customer Group", "Territory"):
			self.assertEqual(linked.count(link_doctype), 1)
		exists.assert_not_called()

	def test_missing_link_record_is_reported_with_its_source_field(self):
		with self.assertRaises(frappe.ValidationError) as raised:
			ec._validate_resolved_fields({"Customer": {"territory": "No Such Territory"}})
		self.assertIn("No Such Territory", str(raised.exception))
		self.assertIn("Customer.territory", str(raised.exception))

	def test_invalid_select_value_still_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			ec._validate_resolved_fields({"Address": {"gst_category": "Not A Category"}})

	def test_blank_values_and_unknown_fields_are_skipped(self):
		ec._validate_resolved_fields({"Customer": {"territory": "", "not_a_field": "x"}})
