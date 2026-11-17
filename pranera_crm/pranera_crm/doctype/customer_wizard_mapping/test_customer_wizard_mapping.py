import frappe
from crm.tests import CRMTestCase

from pranera_crm.pranera_crm.doctype.customer_wizard_mapping.customer_wizard_mapping import get_target_fields

OPTION = {"option_label": "Yes", "option_value": "yes", "mapped_value": "Registered Regular"}


def new_mapping(**kwargs):
	data = {
		"doctype": "Customer Wizard Mapping",
		"question_key": f"_dt_{frappe.generate_hash(length=6)}",
		"label": "Doctype test question?",
		"scope": "Organization",
		"target_doctype": "Address",
		"target_fieldname": "gst_category",
		"question_type": "Fixed",
		"options": [dict(OPTION)],
	}
	data.update(kwargs)
	return frappe.get_doc(data)


class TestCustomerWizardMapping(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def test_named_after_question_key(self):
		doc = new_mapping(question_key="_dt_named").insert()
		self.assertEqual(doc.name, "_dt_named")

	def test_question_key_is_unique(self):
		new_mapping(question_key="_dt_dup").insert()
		with self.assertRaises(frappe.DuplicateEntryError):
			new_mapping(question_key="_dt_dup").insert()

	def test_save_after_editing_an_answer_persists_the_change(self):
		doc = new_mapping().insert()
		doc.options[0].mapped_value = "Unregistered"
		doc.save()
		self.assertEqual(doc.reload().options[0].mapped_value, "Unregistered")

	def test_save_rechecks_every_rule_on_update(self):
		doc = new_mapping().insert()
		doc.target_fieldname = "not_a_real_field"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_delete_removes_the_row(self):
		doc = new_mapping().insert()
		frappe.delete_doc("Customer Wizard Mapping", doc.name)
		self.assertFalse(frappe.db.exists("Customer Wizard Mapping", doc.name))

	def test_dynamic_question_drops_configured_answers(self):
		doc = new_mapping(
			question_type="Dynamic",
			target_doctype="Customer",
			target_fieldname="territory",
			source_doctype="Territory",
		).insert()
		self.assertEqual(doc.options, [])

	def test_dynamic_question_needs_a_valid_source(self):
		with self.assertRaises(frappe.ValidationError):
			new_mapping(question_type="Dynamic", options=[]).insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(
				question_type="Dynamic",
				options=[],
				source_doctype="Territory",
				source_label_field="not_a_field",
			).insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(
				question_type="Dynamic", options=[], source_doctype="Territory", source_filters="{not json"
			).insert()

	def test_fixed_question_clears_a_stale_dynamic_source(self):
		doc = new_mapping(source_doctype="Territory", source_filters="{}").insert()
		self.assertFalse(doc.source_doctype)
		self.assertFalse(doc.source_filters)

	def test_answers_must_be_unique_and_have_at_most_one_default(self):
		with self.assertRaises(frappe.ValidationError):
			new_mapping(options=[dict(OPTION), dict(OPTION)]).insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(
				options=[
					{**OPTION, "is_default": 1},
					{**OPTION, "option_value": "no", "is_default": 1},
				]
			).insert()

	def test_table_fields_can_not_be_targets_but_sales_team_can(self):
		with self.assertRaises(frappe.ValidationError):
			new_mapping(target_doctype="Address", target_fieldname="links").insert()
		new_mapping(
			target_doctype="Customer",
			target_fieldname="sales_team",
			question_type="Dynamic",
			options=[],
			source_doctype="Sales Person",
		).insert()

	def test_secondary_target_needs_both_halves_and_a_real_field(self):
		with self.assertRaises(frappe.ValidationError):
			new_mapping(secondary_target_doctype="Customer").insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(secondary_target_doctype="Customer", secondary_target_fieldname="nope").insert()

	def test_link_and_select_values_are_checked_against_real_masters(self):
		with self.assertRaises(frappe.ValidationError):
			new_mapping(options=[{**OPTION, "mapped_value": "Not A GST Category"}]).insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(
				target_doctype="Customer",
				target_fieldname="territory",
				options=[{**OPTION, "mapped_value": "No Such Territory"}],
			).insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(fallback_value="Not A GST Category").insert()
		new_mapping(fallback_value="Unregistered").insert()

	def test_override_roles_are_a_multiselect_of_real_roles(self):
		doc = new_mapping(override_roles=[{"role": "System Manager"}, {"role": "Sales Manager"}]).insert()
		self.assertEqual(doc.get_override_roles(), ["System Manager", "Sales Manager"])
		with self.assertRaises(frappe.ValidationError):
			new_mapping(override_roles=[{"role": "Not A Real Role"}]).insert()

	def test_duplicate_override_roles_collapse(self):
		doc = new_mapping(override_roles=[{"role": "Sales Manager"}, {"role": "Sales Manager"}]).insert()
		self.assertEqual(doc.get_override_roles(), ["Sales Manager"])

	def test_no_override_roles_means_an_empty_list(self):
		self.assertEqual(new_mapping().insert().get_override_roles(), [])

	def test_branching_fields_are_cleared_without_a_parent(self):
		doc = new_mapping(depends_on_option="yes", depends_on_operator="Is not").insert()
		self.assertFalse(doc.depends_on_option)
		self.assertFalse(doc.depends_on_operator)

	def test_branching_needs_an_answer_and_a_parent_in_the_same_step(self):
		parent = new_mapping().insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(depends_on_question=parent.name).insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(
				scope="Contact",
				target_doctype="Contact",
				target_fieldname="designation",
				depends_on_question=parent.name,
				depends_on_option="yes",
			).insert()
		child = new_mapping(depends_on_question=parent.name, depends_on_option="yes").insert()
		self.assertEqual(child.depends_on_question, parent.name)

	def test_a_question_can_not_depend_on_itself(self):
		doc = new_mapping().insert()
		doc.depends_on_question = doc.name
		doc.depends_on_option = "yes"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_a_dependency_cycle_is_rejected_on_save(self):
		first = new_mapping().insert()
		second = new_mapping(depends_on_question=first.name, depends_on_option="yes").insert()
		first.depends_on_question = second.name
		first.depends_on_option = "yes"
		with self.assertRaises(frappe.ValidationError):
			first.save()


class TestTargetPickers(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_doctype_outside_the_allowed_four_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			new_mapping(target_doctype="User", target_fieldname="first_name").insert()
		with self.assertRaises(frappe.ValidationError):
			new_mapping(secondary_target_doctype="User", secondary_target_fieldname="first_name").insert()

	def test_all_four_doctypes_are_accepted(self):
		for doctype, fieldname in (
			("Customer", "territory"),
			("Address", "gst_category"),
			("Contact", "designation"),
			("CRM Lead", "territory"),
		):
			options = [{**OPTION, "mapped_value": None}]
			new_mapping(target_doctype=doctype, target_fieldname=fieldname, options=options).insert()

	def test_get_target_fields_lists_real_settable_fields_with_labels(self):
		fields = {f["value"]: f["label"] for f in get_target_fields("Customer")}
		self.assertIn("territory", fields)
		self.assertIn("territory", fields["territory"].lower())
		self.assertIn("sales_team", fields)
		meta = frappe.get_meta("Customer")
		for fieldname in fields:
			if fieldname == "sales_team":
				continue
			self.assertNotIn(
				meta.get_field(fieldname).fieldtype, ("Section Break", "Column Break", "Tab Break", "Table")
			)

	def test_every_seeded_target_is_offered_by_the_picker(self):
		import json

		path = frappe.get_app_path("pranera_crm", "data", "customer_wizard_mapping_seed.json")
		with open(path) as f:
			rows = json.load(f)
		for row in rows:
			offered = {f["value"] for f in get_target_fields(row["target_doctype"])}
			self.assertIn(row["target_fieldname"], offered, row["name"])
			if row.get("secondary_target_doctype"):
				offered = {f["value"] for f in get_target_fields(row["secondary_target_doctype"])}
				self.assertIn(row["secondary_target_fieldname"], offered, row["name"])

	def test_get_target_fields_rejects_other_doctypes_and_unauthorised_users(self):
		with self.assertRaises(frappe.ValidationError):
			get_target_fields("User")
		from pranera_crm.tests.test_api import make_user

		frappe.set_user(make_user(roles=[], prefix="cw-picker"))
		with self.assertRaises(frappe.PermissionError):
			get_target_fields("Customer")
