import frappe

from crm.tests import CRMTestCase
from pranera_crm import customer_wizard as cw


def _hash():
	return frappe.generate_hash(length=6)


def _make_user(roles):
	email = f"pranera-cw-test-{_hash()}@example.com"
	return frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "CW Test",
			"send_welcome_email": 0,
			"roles": [{"role": role} for role in roles],
		}
	).insert(ignore_permissions=True).name


def isolate_from_seed_questions():
	"""The app ships real Customer Wizard Mapping rows (fixtures/customer_wizard_mapping.json).
	Tests that call the resolution engine need only their own ad-hoc questions visible,
	so disable the seeded ones for the duration of the test (rolled back in tearDown
	like everything else). Uses the ORM helper, not raw SQL, so each row's document
	cache is invalidated too."""
	names = frappe.get_all("Customer Wizard Mapping", filters={"enabled": 1}, pluck="name")
	for name in names:
		frappe.db.set_value("Customer Wizard Mapping", name, "enabled", 0)
	frappe.clear_cache(doctype="Customer Wizard Mapping")


def make_question(**kwargs):
	data = {
		"doctype": "Customer Wizard Mapping",
		"question_key": f"_test_{_hash()}",
		"label": "Test question?",
		"scope": "Organization",
		"target_doctype": "Address",
		"target_fieldname": "gst_category",
		"question_type": "Fixed",
		"sequence": 0,
	}
	data.update(kwargs)
	return frappe.get_doc(data).insert()


class TestCustomerWizardResolution(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()
		self._created = []

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_simple_fixed_question(self):
		q = make_question(
			options=[
				{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"},
				{"option_label": "No", "option_value": "no", "mapped_value": "Unregistered"},
			]
		)
		result = cw.resolve("Organization", {q.question_key: "yes"})
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Registered Regular")
		self.assertEqual(result["review"][0]["answer"], "Yes")
		self.assertFalse(result["review"][0]["was_fallback"])

	def test_single_option_auto_answers(self):
		q = make_question(
			target_fieldname="payment_terms",
			target_doctype="Customer",
			options=[{"option_label": "Advance", "option_value": "advance", "mapped_value": "100% Advance"}],
		)
		result = cw.resolve("Organization", {})  # nothing answered
		self.assertEqual(result["fields"]["Customer"]["payment_terms"], "100% Advance")
		self.assertTrue(result["review"][0]["auto_answered"])

	def test_fallback_when_unanswered(self):
		# two options, neither default: nothing auto-answers, so the fallback applies
		q = make_question(
			fallback_value="Unregistered",
			options=[
				{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"},
				{"option_label": "No", "option_value": "no", "mapped_value": "Overseas"},
			],
		)
		result = cw.resolve("Organization", {})
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Unregistered")
		self.assertTrue(result["review"][0]["was_fallback"])

	def test_no_fallback_leaves_field_unset(self):
		make_question(
			options=[
				{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"},
				{"option_label": "No", "option_value": "no", "mapped_value": "Overseas"},
			]
		)
		result = cw.resolve("Organization", {})
		self.assertEqual(result["fields"], {})

	def test_branching_visibility(self):
		parent = make_question(
			question_key=f"_test_parent_{_hash()}",
			options=[
				{"option_label": "Yes", "option_value": "yes"},
				{"option_label": "No", "option_value": "no", "mapped_value": "Unregistered"},
			],
		)
		child = make_question(
			depends_on_question=parent.name,
			depends_on_option="yes",
			options=[{"option_label": "Regular", "option_value": "regular", "mapped_value": "Registered Regular"}],
		)

		# parent unanswered (no default -> invisible child)
		self.assertEqual([q.question_key for q in cw.visible_questions("Organization", {})], [parent.question_key])

		# parent answered "no" -> child stays hidden
		visible = cw.visible_questions("Organization", {parent.question_key: "no"})
		self.assertEqual([q.question_key for q in visible], [parent.question_key])

		# parent answered "yes" -> child appears
		visible = cw.visible_questions("Organization", {parent.question_key: "yes"})
		self.assertEqual(
			sorted(q.question_key for q in visible), sorted([parent.question_key, child.question_key])
		)

	def test_overlay_sequential_same_field(self):
		# Mirrors "Regular or Composition?" + "Is it an SEZ unit?", both on gst_category.
		q1 = make_question(
			sequence=1,
			options=[
				{"option_label": "Regular", "option_value": "regular", "mapped_value": "Registered Regular"},
				{"option_label": "Composition", "option_value": "composition", "mapped_value": "Registered Composition"},
			],
		)
		q2 = make_question(
			sequence=2,
			options=[
				{"option_label": "Yes", "option_value": "yes", "mapped_value": "SEZ"},
				{"option_label": "No", "option_value": "no"},  # no mapped_value: leave q1's value alone
			],
		)

		# SEZ = No -> Regular/Composition answer wins
		result = cw.resolve("Organization", {q1.question_key: "composition", q2.question_key: "no"})
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Registered Composition")

		# SEZ = Yes -> overrides whatever q1 set
		result = cw.resolve("Organization", {q1.question_key: "regular", q2.question_key: "yes"})
		self.assertEqual(result["fields"]["Address"]["gst_category"], "SEZ")

	def test_dynamic_question_resolves_live_records(self):
		q = make_question(
			target_doctype="Address",
			target_fieldname="country",
			question_type="Dynamic",
			source_doctype="Country",
			source_label_field="country_name",
			source_filters='{"country_name": "India"}',
		)
		options = cw.resolve_dynamic_options(q, {})
		self.assertEqual(options, [{"label": "India", "value": "India"}])

		result = cw.resolve("Organization", {q.question_key: "India"})
		self.assertEqual(result["fields"]["Address"]["country"], "India")
		self.assertEqual(result["review"][0]["answer"], "India")

	def test_dynamic_filters_interpolate_prior_answer(self):
		territory_q = make_question(
			question_key=f"_test_territory_{_hash()}",
			target_doctype="Customer",
			target_fieldname="territory",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)
		country_q = make_question(
			target_doctype="Address",
			target_fieldname="country",
			question_type="Dynamic",
			source_doctype="Country",
			source_label_field="country_name",
			source_filters='{"country_name": "{{ answers.%s }}"}' % territory_q.question_key,
		)
		# unrelated answer -> the interpolated filter matches nothing
		options = cw.resolve_dynamic_options(country_q, {territory_q.question_key: "no-such-country"})
		self.assertEqual(options, [])
		# real answer -> proves the placeholder was actually substituted, not ignored
		options = cw.resolve_dynamic_options(country_q, {territory_q.question_key: "India"})
		self.assertEqual(options, [{"label": "India", "value": "India"}])

	def test_sales_team_target_is_special_cased(self):
		q = make_question(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			source_doctype="Country",  # any doctype with records; not really Sales Person here
			source_filters='{"country_name": "India"}',
		)
		result = cw.resolve("Organization", {q.question_key: "India"})
		self.assertEqual(result["sales_persons"], ["India"])
		self.assertEqual(result["fields"], {})

	def test_override_requires_configured_role(self):
		q = make_question(
			options=[{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"}],
			override_roles="Sales Manager",
		)
		plain_user = _make_user(roles=["Sales User"])
		manager_user = _make_user(roles=["Sales Manager"])

		result = cw.resolve(
			"Organization", {q.question_key: "yes"}, overrides={q.question_key: "Overseas"}, user=plain_user
		)
		self.assertFalse(result["review"][0]["can_override"])
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Registered Regular")

		result = cw.resolve(
			"Organization", {q.question_key: "yes"}, overrides={q.question_key: "Overseas"}, user=manager_user
		)
		self.assertTrue(result["review"][0]["can_override"])
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Overseas")


class TestCustomerWizardMappingValidation(CRMTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_unknown_target_field_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(target_fieldname="not_a_real_field")

	def test_table_target_rejected_unless_sales_team(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(target_doctype="Address", target_fieldname="links")
		# sales_team on Customer is explicitly allowed
		make_question(target_doctype="Customer", target_fieldname="sales_team", question_type="Dynamic", source_doctype="Country")

	def test_fixed_question_needs_an_option(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(options=[])

	def test_dynamic_question_needs_source_doctype(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(question_type="Dynamic")

	def test_depends_on_option_required_with_depends_on_question(self):
		parent = make_question(options=[{"option_label": "Yes", "option_value": "yes"}])
		with self.assertRaises(frappe.ValidationError):
			make_question(depends_on_question=parent.name, options=[{"option_label": "A", "option_value": "a"}])

	def test_depends_on_question_must_share_scope(self):
		parent = make_question(scope="Organization", options=[{"option_label": "Yes", "option_value": "yes"}])
		with self.assertRaises(frappe.ValidationError):
			make_question(
				scope="Contact",
				target_doctype="Contact",
				target_fieldname="designation",
				depends_on_question=parent.name,
				depends_on_option="yes",
				options=[{"option_label": "A", "option_value": "a"}],
			)

	def test_unknown_override_role_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(
				options=[{"option_label": "Yes", "option_value": "yes"}],
				override_roles="Not A Real Role",
			)
