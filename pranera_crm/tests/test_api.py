import frappe

from crm.tests import CRMTestCase
from pranera_crm.api import LeadAlreadyConverted, convert, get_wizard_context


def _hash():
	return frappe.generate_hash(length=8)


def make_user(roles, prefix="pranera-test"):
	email = f"{prefix}-{_hash()}@example.com"
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": prefix,
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	).insert(ignore_permissions=True)
	return email


def deal_status():
	return frappe.get_all("CRM Deal Status", pluck="name", order_by="position asc", limit=1)[0]


def make_lead(**kwargs):
	suffix = _hash()
	data = {
		"doctype": "CRM Lead",
		"first_name": "Wizard",
		"last_name": suffix,
		"email": f"wizard-{suffix}@example.com",
		"mobile_no": f"+9199{int(suffix[:6], 16) % 10**8:08d}",
		"organization": f"Wizard Org {suffix}",
		"website": f"https://wizard-{suffix}.example.com",
	}
	data.update(kwargs)
	return frappe.get_doc(data).insert()


def make_org(name=None, **kwargs):
	return frappe.get_doc(
		{"doctype": "CRM Organization", "organization_name": name or f"Existing Org {_hash()}", **kwargs}
	).insert()


def make_contact(email=None, first_name="Existing"):
	return frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": first_name,
			"email_ids": [{"email_id": email or f"existing-{_hash()}@example.com", "is_primary": 1}],
		}
	).insert()


class TestConvert(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.deal = {"status": deal_status()}

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# -- permissions ------------------------------------------------------ #

	def test_permission_denied(self):
		lead = make_lead()
		user = make_user(roles=[])

		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			convert(lead.name, deal=self.deal)

		frappe.set_user("Administrator")
		lead.reload()
		self.assertFalse(lead.converted)
		self.assertFalse(frappe.db.exists("CRM Deal", {"lead": lead.name}))

	def test_context_requires_read_permission(self):
		lead = make_lead()
		frappe.set_user(make_user(roles=[]))
		with self.assertRaises(frappe.PermissionError):
			get_wizard_context(lead.name)

	def test_missing_lead(self):
		with self.assertRaises(frappe.DoesNotExistError):
			convert("CRM-LEAD-DOES-NOT-EXIST", deal=self.deal)

	def test_sales_user_can_convert_own_lead(self):
		user = make_user(roles=["Sales User"])
		frappe.set_user(user)
		# CRM restricts leads by owner / assignment / hierarchy
		lead = make_lead(lead_owner=user)
		deal = convert(lead.name, deal=self.deal)
		self.assertEqual(frappe.db.get_value("CRM Deal", deal, "lead"), lead.name)

	# -- guards ----------------------------------------------------------- #

	def test_already_converted(self):
		lead = make_lead()
		first = convert(lead.name, deal=self.deal)

		with self.assertRaises(LeadAlreadyConverted) as ctx:
			convert(lead.name, deal=self.deal)
		self.assertIn(first, str(ctx.exception))
		self.assertEqual(frappe.db.count("CRM Deal", {"lead": lead.name}), 1)

	def test_already_converted_flag_without_deal(self):
		lead = make_lead()
		lead.db_set("converted", 1)
		with self.assertRaises(LeadAlreadyConverted):
			convert(lead.name, deal=self.deal)
		self.assertFalse(frappe.db.exists("CRM Deal", {"lead": lead.name}))

	def test_lost_lead_rejected(self):
		lost = frappe.get_all("CRM Lead Status", filters={"type": "Lost"}, pluck="name", limit=1)
		if not lost:
			self.skipTest("site has no Lost lead status")
		lead = make_lead()
		# skip CRM's "lost reason required" validation, we only need the status type
		lead.db_set("status", lost[0])
		with self.assertRaises(frappe.ValidationError):
			convert(lead.name, deal=self.deal)
		self.assertFalse(frappe.db.exists("CRM Deal", {"lead": lead.name}))

	def test_missing_required_deal_field(self):
		lead = make_lead()
		with self.assertRaises(frappe.MandatoryError):
			convert(lead.name, deal={})
		lead.reload()
		self.assertFalse(lead.converted)

	def test_unknown_existing_records_rejected(self):
		lead = make_lead()
		with self.assertRaises(frappe.DoesNotExistError):
			convert(lead.name, deal=self.deal, existing_organization="No Such Org")
		with self.assertRaises(frappe.DoesNotExistError):
			convert(lead.name, deal=self.deal, existing_contact="No Such Contact")

	def test_deal_payload_is_whitelisted(self):
		lead = make_lead()
		other = make_lead()
		org = make_org()
		deal = convert(
			lead.name,
			deal={
				**self.deal,
				"lead": other.name,
				"organization": org.name,
				"owner": "someone@example.com",
				"not_a_field": 1,
			},
		)
		doc = frappe.get_doc("CRM Deal", deal)
		self.assertEqual(doc.lead, lead.name)
		self.assertNotEqual(doc.organization, org.name)
		self.assertNotEqual(doc.owner, "someone@example.com")

	def test_deal_payload_as_json_string(self):
		lead = make_lead()
		deal = convert(lead.name, deal=frappe.as_json(self.deal))
		self.assertEqual(frappe.db.get_value("CRM Deal", deal, "status"), self.deal["status"])

	# -- happy paths ------------------------------------------------------ #

	def test_new_org_and_new_contact(self):
		lead = make_lead()
		original_org = lead.organization
		renamed = f"Renamed Org {_hash()}"
		new_email = f"renamed-{_hash()}@example.com"

		deal = convert(
			lead.name,
			deal=self.deal,
			lead_updates={
				"organization": renamed,
				"website": "https://renamed.example.com",
				"first_name": "Edited",
				"email": new_email,
			},
		)

		lead.reload()
		self.assertEqual(lead.converted, 1)

		doc = frappe.get_doc("CRM Deal", deal)
		self.assertEqual(doc.lead, lead.name)
		# the Org / Contact were built from the edited values, not the originals
		self.assertEqual(doc.organization, renamed)
		self.assertEqual(frappe.db.get_value("CRM Organization", renamed, "website"), "https://renamed.example.com")
		self.assertFalse(frappe.db.exists("CRM Organization", original_org))

		contact = frappe.get_doc("Contact", doc.contacts[0].contact)
		self.assertEqual(contact.first_name, "Edited")
		self.assertEqual(contact.email_id, new_email)

	def test_new_org_and_new_contact_without_edits(self):
		lead = make_lead()
		orgs = frappe.db.count("CRM Organization")
		contacts = frappe.db.count("Contact")

		deal = convert(lead.name, deal=self.deal)

		self.assertEqual(frappe.db.count("CRM Organization"), orgs + 1)
		self.assertEqual(frappe.db.count("Contact"), contacts + 1)
		doc = frappe.get_doc("CRM Deal", deal)
		self.assertEqual(doc.organization, lead.organization)

	def test_existing_org_and_existing_contact(self):
		lead = make_lead()
		org = make_org()
		contact = make_contact()
		orgs = frappe.db.count("CRM Organization")
		contacts = frappe.db.count("Contact")

		deal = convert(
			lead.name,
			deal=self.deal,
			existing_organization=org.name,
			existing_contact=contact.name,
			# must be ignored: org / contact are not being created
			lead_updates={"organization": "Should Not Exist", "first_name": "Ignored"},
		)

		doc = frappe.get_doc("CRM Deal", deal)
		self.assertEqual(doc.organization, org.name)
		self.assertEqual([c.contact for c in doc.contacts], [contact.name])
		self.assertEqual(frappe.db.count("CRM Organization"), orgs)
		self.assertEqual(frappe.db.count("Contact"), contacts)
		self.assertFalse(frappe.db.exists("CRM Organization", "Should Not Exist"))
		lead.reload()
		self.assertEqual(lead.converted, 1)
		self.assertNotEqual(lead.first_name, "Ignored")


class TestWizardContext(CRMTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_context_shape_and_candidates(self):
		frappe.set_user("Administrator")
		lead = make_lead()
		org = make_org(name=lead.organization, website=lead.website)
		contact = make_contact(email=lead.email)

		ctx = get_wizard_context(lead.name)

		self.assertFalse(ctx["converted"])
		self.assertEqual(ctx["lead"]["name"], lead.name)
		self.assertTrue(ctx["deal_layout"])
		self.assertTrue(ctx["deal_statuses"])
		self.assertEqual(ctx["candidates"]["organizations"][0]["name"], org.name)
		self.assertTrue(ctx["candidates"]["organizations"][0]["exact"])
		self.assertEqual(ctx["candidates"]["auto_organization"], org.name)
		self.assertEqual(ctx["candidates"]["contacts"][0]["name"], contact.name)
		self.assertEqual(ctx["candidates"]["auto_contact"], contact.name)

	def test_context_reports_converted(self):
		frappe.set_user("Administrator")
		lead = make_lead()
		deal = convert(lead.name, deal={"status": deal_status()})
		ctx = get_wizard_context(lead.name)
		self.assertTrue(ctx["converted"])
		self.assertEqual(ctx["deal"], deal)


class TestWhoami(CRMTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_whoami_reports_session_user_and_guest(self):
		from pranera_crm.api import whoami

		frappe.set_user("Administrator")
		self.assertEqual(whoami(), "Administrator")
		frappe.set_user("Guest")
		self.assertEqual(whoami(), "Guest")

	def test_whoami_is_guest_callable(self):
		from pranera_crm.api import whoami

		# the SPA relies on this to tell an expired session from a real 403
		self.assertIn(whoami, frappe.guest_methods)
