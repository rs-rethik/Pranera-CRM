import frappe

from crm.tests import CRMTestCase
from pranera_crm.api import LeadAlreadyConverted, convert, find_candidates, get_wizard_context
from pranera_crm.tests.test_customer_wizard import isolate_from_seed_questions, make_question


def convert_deal(*args, **kwargs):
	"""convert() returns {deal, customer, ...}; most tests only need the deal name."""
	return convert(*args, **kwargs)["deal"]


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


def verify_email(lead, email):
	from pranera_crm import email_verification as ev

	frappe.cache.set_value(ev._key("verified", lead, email), 1, expires_in_sec=ev.VERIFIED_TTL)


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
	lead = frappe.get_doc(data).insert()
	verify_email(lead.name, lead.email)
	return lead


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
		lead = make_lead(lead_owner=user)
		deal = convert_deal(lead.name, deal=self.deal)
		self.assertEqual(frappe.db.get_value("CRM Deal", deal, "lead"), lead.name)

	def test_already_converted(self):
		lead = make_lead()
		first = convert_deal(lead.name, deal=self.deal)

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
		deal = convert_deal(
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
		deal = convert_deal(lead.name, deal=frappe.as_json(self.deal))
		self.assertEqual(frappe.db.get_value("CRM Deal", deal, "status"), self.deal["status"])

	def test_new_org_and_new_contact(self):
		lead = make_lead()
		original_org = lead.organization
		renamed = f"Renamed Org {_hash()}"
		new_email = f"renamed-{_hash()}@example.com"
		verify_email(lead.name, new_email)

		deal = convert_deal(
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

		deal = convert_deal(lead.name, deal=self.deal)

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

		deal = convert_deal(
			lead.name,
			deal=self.deal,
			existing_organization=org.name,
			existing_contact=contact.name,
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


class TestIndividualCustomerSkipsOrganization(CRMTestCase):
	"""An "Individual" answer to customer_type means no CRM Organization gets
	created, regardless of what the client sends for the organization fields —
	see ``api._individual_customer_selected``."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.deal = {"status": deal_status()}

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_individual_answer_overrides_a_client_sent_organization_name(self):
		lead = make_lead()
		orgs = frappe.db.count("CRM Organization")

		deal = convert_deal(
			lead.name,
			deal=self.deal,
			lead_updates={"organization": "Should Not Be Created"},
			customer_answers=frappe.as_json({"customer_type": "individual"}),
		)

		self.assertEqual(frappe.db.count("CRM Organization"), orgs)
		self.assertFalse(frappe.db.exists("CRM Organization", "Should Not Be Created"))
		doc = frappe.get_doc("CRM Deal", deal)
		self.assertFalse(doc.organization)
		lead.reload()
		self.assertFalse(lead.organization)

	def test_company_answer_still_creates_an_organization(self):
		lead = make_lead()
		orgs = frappe.db.count("CRM Organization")

		deal = convert_deal(
			lead.name, deal=self.deal, customer_answers=frappe.as_json({"customer_type": "company"})
		)

		self.assertEqual(frappe.db.count("CRM Organization"), orgs + 1)
		doc = frappe.get_doc("CRM Deal", deal)
		self.assertEqual(doc.organization, lead.organization)

	def test_no_answer_at_all_still_creates_an_organization(self):
		lead = make_lead()
		orgs = frappe.db.count("CRM Organization")

		deal_name = convert_deal(lead.name, deal=self.deal)

		self.assertEqual(frappe.db.count("CRM Organization"), orgs + 1)
		self.assertEqual(frappe.db.get_value("CRM Deal", deal_name, "organization"), lead.organization)

	def test_existing_organization_wins_over_an_individual_answer(self):
		lead = make_lead()
		org = make_org()

		deal = convert_deal(
			lead.name,
			deal=self.deal,
			existing_organization=org.name,
			customer_answers=frappe.as_json({"customer_type": "individual"}),
		)

		doc = frappe.get_doc("CRM Deal", deal)
		self.assertEqual(doc.organization, org.name)

	def test_customer_named_after_contact_when_individual(self):
		frappe.db.set_single_value("ERPNext CRM Settings", "enabled", 1)
		lead = make_lead()
		response = convert(
			lead.name,
			deal=self.deal,
			setup_customer=True,
			customer_answers=frappe.as_json({"customer_type": "individual"}),
		)
		self.assertIsNone(response["customer_error"])
		doc = frappe.get_doc("CRM Deal", response["deal"])
		self.assertFalse(doc.organization)
		contact = frappe.get_doc("Contact", doc.contacts[0].contact)
		customer = frappe.get_doc("Customer", response["customer"])
		self.assertEqual(customer.customer_name, contact.full_name)


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
		deal = convert_deal(lead.name, deal={"status": deal_status()})
		ctx = get_wizard_context(lead.name)
		self.assertTrue(ctx["converted"])
		self.assertEqual(ctx["deal"], deal)

	def test_custom_field_prefill_agrees_with_what_convert_to_deal_actually_copies(self):
		"""_deal_defaults's custom-field matching (pranera's own Deal->Lead lookup)
		must always agree with CRM's own get_matching_custom_deal_field (the
		Lead->Deal direction create_deal() actually uses to auto-copy fields), or
		the wizard's Deal prefill could silently diverge from what convert_to_deal
		actually copies. Regression for the LEAD_DEAL_FIELD_MAP / is_custom_field
		duplication (see README's Q1) — also checks the prefilled *value*, not just
		the fieldname match.

		Deliberately does not call convert_to_deal() or mark the Deal field
		mandatory: both would leave cascading records (a Deal, a new Contact/
		Organization, or a Deal-wide required-field side effect for every other
		test in this process) that Custom Field's own rollback quirk (below) would
		make hard to clean up reliably.
		"""
		frappe.set_user("Administrator")
		suffix = _hash()
		label = f"Prefill Parity {suffix}"
		lead_fieldname = f"custom_prefill_{suffix}"
		deal_fieldname = f"custom_prefill_deal_{suffix}"
		lead_cf_name = f"CRM Lead-{lead_fieldname}"
		deal_cf_name = f"CRM Deal-{deal_fieldname}"

		try:
			frappe.get_doc(
				{"doctype": "Custom Field", "dt": "CRM Lead", "fieldname": lead_fieldname, "label": label, "fieldtype": "Data"}
			).insert(ignore_permissions=True)
			frappe.get_doc(
				{"doctype": "Custom Field", "dt": "CRM Deal", "fieldname": deal_fieldname, "label": label, "fieldtype": "Data"}
			).insert(ignore_permissions=True)
			frappe.clear_cache(doctype="CRM Lead")
			frappe.clear_cache(doctype="CRM Deal")

			from crm.fcrm.doctype.crm_lead.crm_lead import get_matching_custom_deal_field
			from pranera_crm.api import _deal_defaults

			lead_meta = frappe.get_meta("CRM Lead")
			deal_meta = frappe.get_meta("CRM Deal")
			lead_field = lead_meta.get_field(lead_fieldname)
			deal_field = deal_meta.get_field(deal_fieldname)

			self.assertEqual(get_matching_custom_deal_field(lead_field, deal_meta), deal_fieldname)

			lead = make_lead(**{lead_fieldname: "Shared Value"})
			defaults = _deal_defaults(lead, [deal_field])
			self.assertEqual(defaults.get(deal_fieldname), "Shared Value")
		finally:
			if frappe.db.exists("CRM Lead", locals().get("lead", frappe._dict()).get("name")):
				frappe.delete_doc("CRM Lead", lead.name, ignore_permissions=True, force=True)
			for cf_name in (lead_cf_name, deal_cf_name):
				if frappe.db.exists("Custom Field", cf_name):
					frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True, force=True)
			frappe.clear_cache(doctype="CRM Lead")
			frappe.clear_cache(doctype="CRM Deal")
			frappe.db.commit()

	def test_auto_organization_hidden_without_permission(self):
		"""S1: auto_organization must be permission-filtered like the rest of
		find_candidates — a user who can't read a same-named CRM Organization must
		not learn it exists, even though its name is an exact match."""
		frappe.set_user("Administrator")
		org = make_org()
		other_org = make_org()
		user = make_user(roles=["Sales User"], prefix="cw-org-noperm")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "CRM Organization",
				"for_value": other_org.name,
			}
		).insert(ignore_permissions=True)

		frappe.set_user(user)
		result = find_candidates(organization=org.organization_name)
		self.assertIsNone(result["auto_organization"])

	def test_auto_organization_resolves_normally_without_a_restriction(self):
		frappe.set_user("Administrator")
		org = make_org()
		user = make_user(roles=["Sales User"], prefix="cw-org-ok")

		frappe.set_user(user)
		result = find_candidates(organization=org.organization_name)
		self.assertEqual(result["auto_organization"], org.name)

	def test_like_wildcards_escaped(self):
		"""S4: a literal %/_ in the search term must not act as a SQL wildcard."""
		frappe.set_user("Administrator")
		target = make_org(name=f"100% Corp {_hash()}")
		decoy = make_org()

		result = find_candidates(organization=target.organization_name)
		names = {r["name"] for r in result["organizations"]}
		self.assertIn(target.name, names)
		self.assertNotIn(decoy.name, names)


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

		self.assertIn(whoami, frappe.guest_methods)


class TestWizardSwitch(CRMTestCase):
	"""CRM Settings > Enable Convert to Deal Wizard"""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _set(self, value):
		from pranera_crm.settings import ENABLE_FIELD, SETTINGS

		frappe.db.set_single_value(SETTINGS, ENABLE_FIELD, value)

	def test_custom_field_exists_on_crm_settings(self):
		from pranera_crm.settings import ENABLE_FIELD, SETTINGS

		df = frappe.get_meta(SETTINGS).get_field(ENABLE_FIELD)
		self.assertIsNotNone(df)
		self.assertEqual(df.fieldtype, "Check")
		self.assertEqual(str(df.default), "1")

	def test_enabled_by_default_when_never_saved(self):
		from pranera_crm.settings import ENABLE_FIELD, SETTINGS, is_wizard_enabled

		frappe.db.sql("delete from `tabSingles` where `doctype` = %s and `field` = %s", (SETTINGS, ENABLE_FIELD))
		self.assertTrue(is_wizard_enabled())

	def test_ticked_and_unticked(self):
		from pranera_crm.api import wizard_enabled

		self._set(1)
		self.assertTrue(wizard_enabled())
		self._set(0)
		self.assertFalse(wizard_enabled())

	def test_disabled_blocks_every_wizard_api(self):
		from pranera_crm.api import WizardDisabled, search_candidates

		lead = make_lead()
		self._set(0)

		with self.assertRaises(WizardDisabled):
			get_wizard_context(lead.name)
		with self.assertRaises(WizardDisabled):
			search_candidates(lead.name)
		with self.assertRaises(WizardDisabled):
			convert(lead.name, deal={"status": deal_status()})

		lead.reload()
		self.assertFalse(lead.converted)
		from crm.fcrm.doctype.crm_lead.crm_lead import convert_to_deal

		self.assertTrue(convert_to_deal(lead=lead.name, deal={"status": deal_status()}))

	def test_reenabled_wizard_works_again(self):
		lead = make_lead()
		self._set(0)
		self._set(1)
		self.assertTrue(convert_deal(lead.name, deal={"status": deal_status()}))

	def test_default_is_written_once_and_never_overwrites_an_admin_choice(self):
		from pranera_crm.settings import DEFAULT_APPLIED, ensure_default, is_wizard_enabled

		frappe.db.set_default(DEFAULT_APPLIED, "")
		self._set(0)
		ensure_default()
		self.assertTrue(is_wizard_enabled())

		self._set(0)
		ensure_default()
		self.assertFalse(is_wizard_enabled())

	def test_redirect_target_when_disabled(self):
		from pranera_crm.www.deal_wizard import crm_url_for_request

		previous = getattr(frappe.local, "request", None)
		try:
			frappe.local.request = frappe._dict(path="/deal_wizard/CRM-LEAD-2026-00001")
			self.assertEqual(crm_url_for_request(), "/crm/leads/CRM-LEAD-2026-00001")
			frappe.local.request = frappe._dict(path="/deal_wizard/")
			self.assertEqual(crm_url_for_request(), "/crm")
			frappe.local.request = frappe._dict(path="/deal_wizard")
			self.assertEqual(crm_url_for_request(), "/crm")
		finally:
			frappe.local.request = previous


class TestSiteProperties(CRMTestCase):
	def test_follows_system_settings(self):
		from pranera_crm.settings import get_site_properties

		props = get_site_properties()
		for key in ("lang", "rtl", "timezone", "date_format", "number_format", "currency", "brand"):
			self.assertIn(key, props)
		self.assertEqual(props["date_format"], frappe.get_system_settings("date_format"))
		self.assertEqual(props["number_format"], frappe.get_system_settings("number_format"))
		self.assertEqual(props["lang"], frappe.local.lang)
		self.assertIn("system", props["timezone"])
		self.assertIn("name", props["brand"])


class TestLeadQuestionResolution(CRMTestCase):
	"""Territory/Industry/Salutation/Gender-style questions: resolved server-side
	from ``customer_answers``/``contact_customer_answers`` and applied to the Lead
	*before* conversion, regardless of the ERPNext bridge — see
	``pranera_crm.api._resolve_lead_questions``."""

	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()
		self.deal = {"status": deal_status()}

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_resolved_answer_applied_to_new_organization(self):
		q = make_question(
			requires_erpnext_bridge=0,
			target_doctype="CRM Lead",
			target_fieldname="territory",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)
		lead = make_lead()
		deal = convert_deal(lead.name, deal=self.deal, customer_answers={q.question_key: "india"})
		organization = frappe.db.get_value("CRM Deal", deal, "organization")
		self.assertEqual(frappe.db.get_value("CRM Organization", organization, "territory"), "India")

	def test_resolved_answer_applied_to_new_contact(self):
		q = make_question(
			requires_erpnext_bridge=0,
			scope="Contact",
			target_doctype="CRM Lead",
			target_fieldname="salutation",
			options=[{"option_label": "Dr", "option_value": "dr", "mapped_value": "Dr"}],
		)
		lead = make_lead()
		deal = convert_deal(lead.name, deal=self.deal, contact_customer_answers={q.question_key: "dr"})
		contact = frappe.get_doc("CRM Deal", deal).contacts[0].contact
		self.assertEqual(frappe.db.get_value("Contact", contact, "salutation"), "Dr")

	def test_skipped_for_an_existing_organization(self):
		q = make_question(
			requires_erpnext_bridge=0,
			target_doctype="CRM Lead",
			target_fieldname="territory",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)
		lead = make_lead()
		org = make_org()
		convert_deal(
			lead.name,
			deal=self.deal,
			existing_organization=org.name,
			customer_answers={q.question_key: "india"},
		)
		self.assertNotEqual(frappe.db.get_value("CRM Organization", org.name, "territory"), "India")

	def test_applies_even_when_erpnext_bridge_declined(self):
		"""Territory/Industry-style questions apply whether or not the caller asked
		for ERPNext Customer setup — they aren't an ERPNext-only concern."""
		q = make_question(
			requires_erpnext_bridge=0,
			target_doctype="CRM Lead",
			target_fieldname="territory",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)
		lead = make_lead()
		deal = convert_deal(
			lead.name, deal=self.deal, setup_customer=False, customer_answers={q.question_key: "india"}
		)
		organization = frappe.db.get_value("CRM Deal", deal, "organization")
		self.assertEqual(frappe.db.get_value("CRM Organization", organization, "territory"), "India")

	def test_bridge_only_mandatory_question_does_not_block_a_declined_setup(self):
		"""A mandatory ERPNext-only question must not block conversion when the
		caller never asked for ERPNext Customer setup in the first place."""
		make_question(
			requires_erpnext_bridge=1,
			is_mandatory=1,
			target_doctype="Customer",
			target_fieldname="customer_group",
			options=[
				{"option_label": "A", "option_value": "a", "mapped_value": "Commercial"},
				{"option_label": "B", "option_value": "b", "mapped_value": "Individual"},
			],
		)
		lead = make_lead()
		deal = convert_deal(lead.name, deal=self.deal, setup_customer=False)
		self.assertTrue(frappe.db.exists("CRM Deal", deal))
