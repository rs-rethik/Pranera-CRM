import json

import frappe


def execute():
	"""Customer Group used to offer "Individual" alongside the business groups
	regardless of the Individual/Business answer, allowing a Company Customer in
	the Individual group. Split it by customer type on sites seeded before this."""
	if not frappe.db.exists("Customer Wizard Mapping", "customer_group"):
		return
	group = frappe.get_doc("Customer Wizard Mapping", "customer_group")
	if group.depends_on_question or not any(o.option_value == "individual" for o in group.options):
		return

	group.options = [o for o in group.options if o.option_value != "individual"]
	group.depends_on_question = "customer_type"
	group.depends_on_option = "individual"
	group.depends_on_operator = "Is not"
	group.save()

	if not frappe.db.exists("Customer Wizard Mapping", "customer_group_individual"):
		path = frappe.get_app_path("pranera_crm", "data", "customer_wizard_mapping_seed.json")
		with open(path) as f:
			row = next(r for r in json.load(f) if r["name"] == "customer_group_individual")
		frappe.get_doc(row).insert()
