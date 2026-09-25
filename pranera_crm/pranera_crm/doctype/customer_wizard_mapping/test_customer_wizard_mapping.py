import frappe
from crm.tests import CRMTestCase

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

	def test_override_roles_are_normalised_and_checked(self):
		doc = new_mapping(override_roles="  System Manager \n\n Sales Manager  ").insert()
		self.assertEqual(doc.override_roles, "System Manager\nSales Manager")
		self.assertEqual(doc.get_override_roles(), ["System Manager", "Sales Manager"])
		with self.assertRaises(frappe.ValidationError):
			new_mapping(override_roles="Not A Real Role").insert()

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
