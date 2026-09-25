import frappe
from crm.tests import CRMTestCase

from pranera_crm import customer_wizard as cw


def _hash():
	return frappe.generate_hash(length=6)


def _make_user(roles):
	email = f"pranera-cw-test-{_hash()}@example.com"
	return (
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "CW Test",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


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
		make_question(
			target_fieldname="payment_terms",
			target_doctype="Customer",
			options=[{"option_label": "Advance", "option_value": "advance", "mapped_value": "100% Advance"}],
		)
		result = cw.resolve("Organization", {})
		self.assertEqual(result["fields"]["Customer"]["payment_terms"], "100% Advance")
		self.assertTrue(result["review"][0]["auto_answered"])

	def test_fallback_when_unanswered(self):
		make_question(
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

	def test_empty_string_answer_treated_as_unanswered(self):
		"""E4: a direct API caller sending "" for an answer must be treated the same
		as not answering at all — not "not one of the available answers"."""
		q = make_question(
			fallback_value="Unregistered",
			options=[
				{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"},
				{"option_label": "No", "option_value": "no", "mapped_value": "Overseas"},
			],
		)
		result = cw.resolve("Organization", {q.question_key: ""})
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Unregistered")
		self.assertTrue(result["review"][0]["was_fallback"])

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
			options=[
				{"option_label": "Regular", "option_value": "regular", "mapped_value": "Registered Regular"}
			],
		)

		self.assertEqual(
			[q.question_key for q in cw.visible_questions("Organization", {})], [parent.question_key]
		)

		visible = cw.visible_questions("Organization", {parent.question_key: "no"})
		self.assertEqual([q.question_key for q in visible], [parent.question_key])

		visible = cw.visible_questions("Organization", {parent.question_key: "yes"})
		self.assertEqual(
			sorted(q.question_key for q in visible), sorted([parent.question_key, child.question_key])
		)

	def test_overlay_sequential_same_field(self):
		q1 = make_question(
			sequence=1,
			options=[
				{"option_label": "Regular", "option_value": "regular", "mapped_value": "Registered Regular"},
				{
					"option_label": "Composition",
					"option_value": "composition",
					"mapped_value": "Registered Composition",
				},
			],
		)
		q2 = make_question(
			sequence=2,
			options=[
				{"option_label": "Yes", "option_value": "yes", "mapped_value": "SEZ"},
				{"option_label": "No", "option_value": "no"},
			],
		)

		result = cw.resolve("Organization", {q1.question_key: "composition", q2.question_key: "no"})
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Registered Composition")

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
			source_filters=f'{{"country_name": "{{{{ answers.{territory_q.question_key} }}}}"}}',
		)
		options = cw.resolve_dynamic_options(country_q, {territory_q.question_key: "no-such-country"})
		self.assertEqual(options, [])
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
			override_roles=[{"role": "Sales Manager"}],
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
		make_question(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			source_doctype="Country",
		)

	def test_fixed_question_needs_an_option(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(options=[])

	def test_dynamic_question_needs_source_doctype(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(question_type="Dynamic")

	def test_depends_on_option_required_with_depends_on_question(self):
		parent = make_question(options=[{"option_label": "Yes", "option_value": "yes"}])
		with self.assertRaises(frappe.ValidationError):
			make_question(
				depends_on_question=parent.name, options=[{"option_label": "A", "option_value": "a"}]
			)

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
				override_roles=[{"role": "Not A Real Role"}],
			)

	def test_secondary_target_requires_both_doctype_and_fieldname(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(
				options=[{"option_label": "Yes", "option_value": "yes"}],
				secondary_target_doctype="Customer",
			)
		with self.assertRaises(frappe.ValidationError):
			make_question(
				options=[{"option_label": "Yes", "option_value": "yes"}],
				secondary_target_fieldname="territory",
			)

	def test_unknown_secondary_target_field_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(
				options=[{"option_label": "Yes", "option_value": "yes"}],
				secondary_target_doctype="Customer",
				secondary_target_fieldname="not_a_real_field",
			)

	def test_valid_secondary_target_accepted(self):
		q = make_question(
			target_doctype="CRM Lead",
			target_fieldname="territory",
			secondary_target_doctype="Customer",
			secondary_target_fieldname="territory",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)
		self.assertEqual(q.secondary_target_doctype, "Customer")

	def test_mapping_with_missing_link_master_rejected_at_save(self):
		"""E1: a mapped_value pointed at a Link field must reference a real record —
		caught here, not surfaced later as an unfixable customer_error or a raw
		LinkValidationError mid-convert."""
		with self.assertRaises(frappe.ValidationError):
			make_question(
				target_doctype="Customer",
				target_fieldname="territory",
				options=[
					{
						"option_label": "Nowhere",
						"option_value": "nowhere",
						"mapped_value": "Not A Real Territory",
					}
				],
			)

	def test_mapping_with_invalid_select_value_rejected_at_save(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(
				options=[{"option_label": "Bad", "option_value": "bad", "mapped_value": "Not A GST Category"}]
			)

	def test_mapping_with_bad_fallback_value_rejected_at_save(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(
				fallback_value="Not A GST Category",
				options=[
					{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"}
				],
			)

	def test_mapping_with_bad_secondary_mapped_value_rejected_at_save(self):
		with self.assertRaises(frappe.ValidationError):
			make_question(
				target_doctype="CRM Lead",
				target_fieldname="territory",
				secondary_target_doctype="Customer",
				secondary_target_fieldname="territory",
				options=[
					{
						"option_label": "India",
						"option_value": "india",
						"mapped_value": "India",
						"secondary_mapped_value": "Not A Real Territory",
					}
				],
			)

	def test_mapping_with_valid_master_values_saves_fine(self):
		make_question(
			target_doctype="Customer",
			target_fieldname="territory",
			fallback_value="India",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)


class TestMandatoryAndOperatorRules(CRMTestCase):
	"""The mandatory flag and the "Is not" branching operator added to the engine."""

	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_is_not_operator(self):
		parent = make_question(
			options=[
				{"option_label": "India", "option_value": "india"},
				{"option_label": "Elsewhere", "option_value": "elsewhere"},
			],
		)
		child = make_question(
			target_doctype="Customer",
			target_fieldname="gst_category",
			depends_on_question=parent.question_key,
			depends_on_option="india",
			depends_on_operator="Is not",
			options=[{"option_label": "Overseas", "option_value": "overseas", "mapped_value": "Overseas"}],
		)

		self.assertTrue(cw.is_visible(child, {parent.question_key: "elsewhere"}))
		self.assertFalse(cw.is_visible(child, {parent.question_key: "india"}))
		self.assertFalse(cw.is_visible(child, {}))

	def test_is_not_resolution(self):
		parent = make_question(
			options=[
				{"option_label": "India", "option_value": "india"},
				{"option_label": "Elsewhere", "option_value": "elsewhere"},
			],
		)
		child = make_question(
			target_doctype="Customer",
			target_fieldname="gst_category",
			depends_on_question=parent.question_key,
			depends_on_option="india",
			depends_on_operator="Is not",
			options=[{"option_label": "Overseas", "option_value": "overseas", "mapped_value": "Overseas"}],
		)
		result = cw.resolve(
			"Organization", {parent.question_key: "elsewhere", child.question_key: "overseas"}
		)
		self.assertEqual(result["fields"]["Customer"]["gst_category"], "Overseas")
		result = cw.resolve("Organization", {parent.question_key: "india", child.question_key: "overseas"})
		self.assertNotIn("Customer", result["fields"])

	def test_mandatory_blocks_when_unanswered(self):
		make_question(
			is_mandatory=1,
			options=[
				{"option_label": "A", "option_value": "a", "mapped_value": "Registered Regular"},
				{"option_label": "B", "option_value": "b", "mapped_value": "Unregistered"},
			],
		)
		with self.assertRaises(frappe.ValidationError):
			cw.resolve("Organization", {})

	def test_mandatory_satisfied_by_fallback(self):
		q = make_question(
			is_mandatory=1,
			fallback_value="Unregistered",
			options=[
				{"option_label": "Yes", "option_value": "yes"},
				{"option_label": "No", "option_value": "no"},
			],
		)
		result = cw.resolve("Organization", {})
		row = next(r for r in result["review"] if r["question_key"] == q.question_key)
		self.assertTrue(row["was_fallback"])
		self.assertEqual(row["value"], "Unregistered")

	def test_mandatory_satisfied_by_default_answer(self):
		q = make_question(
			is_mandatory=1,
			options=[
				{
					"option_label": "Only",
					"option_value": "only",
					"mapped_value": "Unregistered",
					"is_default": 1,
				},
				{"option_label": "Other", "option_value": "other", "mapped_value": "Registered Regular"},
			],
		)
		result = cw.resolve("Organization", {})
		row = next(r for r in result["review"] if r["question_key"] == q.question_key)
		self.assertEqual(row["value"], "Unregistered")

	def test_answered_option_without_mapped_value_still_satisfies_mandatory(self):
		q = make_question(
			is_mandatory=1,
			options=[
				{"option_label": "Yes", "option_value": "yes"},
				{"option_label": "No", "option_value": "no", "mapped_value": "Unregistered"},
			],
		)
		result = cw.resolve("Organization", {q.question_key: "yes"})
		row = next(r for r in result["review"] if r["question_key"] == q.question_key)
		self.assertFalse(row["was_fallback"])

	def test_unknown_fixed_answer_rejected(self):
		q = make_question(
			options=[{"option_label": "No", "option_value": "no", "mapped_value": "Unregistered"}],
		)
		with self.assertRaises(frappe.ValidationError):
			cw.resolve("Organization", {q.question_key: "not-a-configured-answer"})

	def test_payload_carries_mandatory_operator_and_fallback(self):
		q = make_question(
			is_mandatory=1,
			fallback_value="Unregistered",
			options=[{"option_label": "INR", "option_value": "inr", "mapped_value": "Registered Regular"}],
		)
		payload = cw.question_payload(q, {})
		self.assertTrue(payload["is_mandatory"])
		self.assertEqual(payload["depends_on_operator"], "Is")
		self.assertEqual(payload["fallback_value"], "Unregistered")

	def test_payload_carries_target_meta_and_mapped_values(self):
		"""The Review step shows resolved values, not questions: it needs the target
		field's meta and each answer's mapped value."""
		q = make_question(
			target_doctype="Customer",
			target_fieldname="customer_group",
			options=[
				{"option_label": "Commercial", "option_value": "commercial", "mapped_value": "Commercial"}
			],
		)
		payload = cw.question_payload(q, {})
		self.assertEqual(payload["target_label"], "Customer Group")
		self.assertEqual(payload["target_fieldtype"], "Link")
		self.assertEqual(payload["target_field_options"], "Customer Group")
		self.assertEqual(payload["options"][0]["mapped_value"], "Commercial")

		sp = make_question(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			source_doctype="Sales Person",
		)
		payload = cw.question_payload(sp, {})
		self.assertEqual(payload["target_label"], "Sales Person")
		self.assertEqual(payload["target_fieldtype"], "Link")
		self.assertEqual(payload["target_field_options"], "Sales Person")


class TestBridgeAwareness(CRMTestCase):
	"""``requires_erpnext_bridge`` / ``include_bridge_questions``: a question that
	applies regardless of the ERPNext bridge (e.g. Territory) must still be asked,
	resolved and mandatory-checked when the bridge-only questions are excluded."""

	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_bridge_only_question_excluded_when_not_included(self):
		bridge_q = make_question(
			requires_erpnext_bridge=1,
			options=[{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"}],
		)
		always_q = make_question(
			requires_erpnext_bridge=0,
			target_doctype="Customer",
			target_fieldname="territory",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)

		keys = {q.question_key for q in cw.get_questions("Organization", include_bridge_questions=False)}
		self.assertEqual(keys, {always_q.question_key})

		keys = {q.question_key for q in cw.get_questions("Organization", include_bridge_questions=True)}
		self.assertEqual(keys, {bridge_q.question_key, always_q.question_key})

	def test_bridge_only_mandatory_question_does_not_block_when_excluded(self):
		make_question(
			requires_erpnext_bridge=1,
			is_mandatory=1,
			options=[
				{"option_label": "A", "option_value": "a", "mapped_value": "Registered Regular"},
				{"option_label": "B", "option_value": "b", "mapped_value": "Unregistered"},
			],
		)
		make_question(
			requires_erpnext_bridge=0,
			target_doctype="Customer",
			target_fieldname="territory",
			options=[{"option_label": "India", "option_value": "india", "mapped_value": "India"}],
		)

		result = cw.resolve("Organization", {}, include_bridge_questions=False)
		self.assertEqual(result["fields"]["Customer"]["territory"], "India")

		with self.assertRaises(frappe.ValidationError):
			cw.resolve("Organization", {}, include_bridge_questions=True)


class TestSecondaryTarget(CRMTestCase):
	"""A question's answer can also be written onto a second field (e.g. Territory
	feeding both CRM Organization/CRM Lead and the ERPNext Customer)."""

	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_secondary_target_written_alongside_primary(self):
		q = make_question(
			target_doctype="CRM Lead",
			target_fieldname="territory",
			secondary_target_doctype="Customer",
			secondary_target_fieldname="territory",
			options=[
				{
					"option_label": "India",
					"option_value": "india",
					"mapped_value": "India",
					"secondary_mapped_value": "India",
				},
			],
		)
		result = cw.resolve("Organization", {q.question_key: "india"})
		self.assertEqual(result["fields"]["CRM Lead"]["territory"], "India")
		self.assertEqual(result["fields"]["Customer"]["territory"], "India")

	def test_secondary_target_skipped_when_option_has_no_secondary_value(self):
		q = make_question(
			target_doctype="Address",
			target_fieldname="gst_category",
			secondary_target_doctype="Customer",
			secondary_target_fieldname="tax_category",
			options=[
				{"option_label": "Regular", "option_value": "regular", "mapped_value": "Registered Regular"},
				{
					"option_label": "Composition",
					"option_value": "composition",
					"mapped_value": "Registered Composition",
					"secondary_mapped_value": "Registered Composition",
				},
			],
		)
		result = cw.resolve("Organization", {q.question_key: "regular"})
		self.assertEqual(result["fields"]["Address"]["gst_category"], "Registered Regular")
		self.assertNotIn("Customer", result["fields"])

		result = cw.resolve("Organization", {q.question_key: "composition"})
		self.assertEqual(result["fields"]["Customer"]["tax_category"], "Registered Composition")

	def test_override_does_not_write_a_stale_secondary_value(self):
		"""An override only speaks to the question's own primary target — the
		secondary target must not still receive the un-overridden option's value."""
		q = make_question(
			target_doctype="CRM Lead",
			target_fieldname="territory",
			secondary_target_doctype="Customer",
			secondary_target_fieldname="territory",
			override_roles=[{"role": "Sales Manager"}],
			options=[
				{
					"option_label": "India",
					"option_value": "india",
					"mapped_value": "India",
					"secondary_mapped_value": "India",
				},
			],
		)
		manager = _make_user(roles=["Sales Manager"])
		result = cw.resolve(
			"Organization",
			{q.question_key: "india"},
			overrides={q.question_key: "Chennai Region"},
			user=manager,
		)
		self.assertEqual(result["fields"]["CRM Lead"]["territory"], "Chennai Region")
		self.assertNotIn("Customer", result["fields"])


class TestDisabledQuestionVisibility(CRMTestCase):
	"""A disabled question (or a disabled parent) must never resolve, on either
	side — not just be hidden from the list the client renders."""

	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_disabled_question_is_never_visible(self):
		q = make_question(
			options=[{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"}]
		)
		frappe.db.set_value("Customer Wizard Mapping", q.name, "enabled", 0)
		frappe.clear_cache(doctype="Customer Wizard Mapping")
		self.assertFalse(cw.is_visible(frappe.get_cached_doc("Customer Wizard Mapping", q.name), {}))

	def test_disabled_parent_hides_children_server_side(self):
		parent = make_question(
			options=[{"option_label": "Yes", "option_value": "yes", "mapped_value": None, "is_default": 1}]
		)
		make_question(
			target_doctype="Customer",
			target_fieldname="gst_category",
			depends_on_question=parent.name,
			depends_on_option="yes",
			options=[
				{"option_label": "Regular", "option_value": "regular", "mapped_value": "Registered Regular"}
			],
		)
		result = cw.resolve("Organization", {})
		self.assertEqual(result["fields"]["Customer"]["gst_category"], "Registered Regular")

		frappe.db.set_value("Customer Wizard Mapping", parent.name, "enabled", 0)
		frappe.clear_cache(doctype="Customer Wizard Mapping")
		result = cw.resolve("Organization", {})
		self.assertNotIn("Customer", result["fields"])
		self.assertEqual([r["question_key"] for r in result["review"]], [])


class TestDynamicSourceUnreadable(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		isolate_from_seed_questions()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_unreadable_source_doctype_degrades_to_empty_options(self):
		user = _make_user(roles=["Sales User"])
		q = make_question(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			source_doctype="DocType",
		)
		frappe.set_user(user)
		try:
			options = cw.resolve_dynamic_options(q, {})
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(options, [])


class TestCustomerWizardMappingPermissions(CRMTestCase):
	"""S2: these rows control what gets written onto ERPNext Customers (customer
	groups, GST categories, sales-team members) — only System Manager (or a
	dedicated config role) should be able to change them, not a sales role."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_sales_manager_cannot_edit_mapping(self):
		user = _make_user(roles=["Sales Manager"])
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			make_question(options=[{"option_label": "Yes", "option_value": "yes", "mapped_value": "X"}])

	def test_system_manager_can_still_edit_mapping(self):
		user = _make_user(roles=["System Manager"])
		frappe.set_user(user)
		make_question(
			options=[{"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"}]
		)
