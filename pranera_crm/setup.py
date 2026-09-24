import json

import frappe

from pranera_crm.settings import ensure_default

ERPNEXT_SYNC_DEFAULT_APPLIED = "pranera_crm_erpnext_sync_default_applied"

FORM_SCRIPT = "Pranera Convert Wizard"
_form_script_enabled_before_sync = {}


def before_migrate():
	"""Capture the Form Script's current `enabled` state before fixture sync (which
	runs later in this same `bench migrate`) unconditionally resets it back to the
	shipped default — see `restore_form_script_enabled_state`."""
	if frappe.db.exists("CRM Form Script", FORM_SCRIPT):
		_form_script_enabled_before_sync["enabled"] = frappe.db.get_value(
			"CRM Form Script", FORM_SCRIPT, "enabled"
		)


def after_install():
	ensure_default()
	ensure_payment_terms_template()
	ensure_territories()
	ensure_customer_wizard_questions()
	ensure_erpnext_customer_sync_disabled()
	remove_sales_person_question()


def after_migrate():
	restore_form_script_enabled_state()
	ensure_default()
	ensure_payment_terms_template()
	ensure_territories()
	ensure_customer_wizard_questions()
	ensure_erpnext_customer_sync_disabled()
	remove_sales_person_question()


def restore_form_script_enabled_state():
	"""Fixture sync (which runs before `after_migrate`, inside the same `bench
	migrate`) always re-imports the CRM Form Script fixture, including its pinned
	`enabled: 1` — silently undoing an admin's deliberate disable. Restore
	whatever `before_migrate` captured just before that happened. A no-op on
	install (nothing was captured, since the doc didn't exist yet)."""
	if "enabled" not in _form_script_enabled_before_sync:
		return
	enabled = _form_script_enabled_before_sync.pop("enabled")
	if frappe.db.exists("CRM Form Script", FORM_SCRIPT):
		frappe.db.set_value("CRM Form Script", FORM_SCRIPT, "enabled", enabled)


def ensure_payment_terms_template():
	"""The seeded "payment_terms" Customer Wizard Mapping question points at this
	template; the site ships with none, so create it once (never touched again)."""
	name = "100% Advance"
	if frappe.db.exists("Payment Terms Template", name):
		return
	frappe.get_doc(
		{
			"doctype": "Payment Terms Template",
			"template_name": name,
			"terms": [
				{
					"invoice_portion": 100,
					"due_date_based_on": "Day(s) after invoice date",
					"credit_days": 0,
					"description": "100% payable in advance",
				}
			],
		}
	).insert(ignore_permissions=True)


def ensure_territories():
	"""The seeded "territory" Customer Wizard Mapping question resolves onto
	CRM Organization/CRM Lead's own Territory field (primary target, a Link to
	CRM Territory) and Customer.territory (secondary target, a Link to ERPNext's
	own, separate Territory doctype). CRM Territory ships with no records at all;
	ERPNext's own Territory only gets "India"/"Rest Of The World" from the setup
	wizard if the site's country was India — seed both the same way, once, so a
	non-India-setup-wizard site doesn't hit an unfixable Link-validation error the
	first time this question resolves to "India"."""
	for name in ("India", "Rest Of The World"):
		if not frappe.db.exists("CRM Territory", name):
			frappe.get_doc({"doctype": "CRM Territory", "territory_name": name}).insert(
				ignore_permissions=True
			)
		if not frappe.db.exists("Territory", name):
			frappe.get_doc({"doctype": "Territory", "territory_name": name}).insert(ignore_permissions=True)


def ensure_customer_wizard_questions():
	"""Seed the shipped Customer Wizard Mapping questions once — deliberately kept
	out of pranera_crm/fixtures/ entirely, not just out of the `fixtures` hook
	list. `frappe.utils.fixtures.import_fixtures` lists every *.json file
	physically inside an app's fixtures/ folder and imports each one
	unconditionally; it never consults hooks.py's `fixtures` declaration at all
	(that list is only ever read by *export*) — so a JSON file left in that
	folder gets deleted-and-reinserted (force) on every `bench migrate`
	regardless of whether anything in hooks.py still references it. That would
	silently wipe any admin edit to a seeded row (an `enabled` flag, a
	`mapped_value`, an option) back to the shipped default on the very next
	migrate — the opposite of the "edit, disable or add to these freely" the
	README promises. The same JSON the app used to ship as a fixture now lives in
	pranera_crm/data/ instead (pure seed data, not re-transcribed into Python,
	just relocated out of the one folder Frappe auto-syncs); each row is
	inserted only if its name doesn't already exist — a row that's already
	there, whether unedited or admin-customized, is never touched again."""
	path = frappe.get_app_path("pranera_crm", "data", "customer_wizard_mapping_seed.json")
	with open(path) as f:
		rows = json.load(f)
	for row in rows:
		if frappe.db.exists("Customer Wizard Mapping", row["name"]):
			continue
		frappe.get_doc(row).insert(ignore_permissions=True)


def ensure_erpnext_customer_sync_disabled():
	"""The wizard is meant to be the only place a Customer gets created from a
	Deal. CRM's own `ERPNext CRM Settings.create_customer_on_status_change`
	(separate from the `.enabled` flag pranera_crm's own bridge already checks)
	drives a `CRM Deal.on_update` hook that creates a Customer with no check for
	one the wizard already created — so default that setting off, once, the same
	"set it, never fight an admin's later choice" way `settings.ensure_default`
	handles the wizard's own switch."""
	settings = "ERPNext CRM Settings"
	field = "create_customer_on_status_change"
	if not frappe.get_meta(settings).has_field(field):
		return
	if frappe.db.get_default(ERPNEXT_SYNC_DEFAULT_APPLIED):
		return

	frappe.db.set_single_value(settings, field, 0)
	frappe.db.set_default(ERPNEXT_SYNC_DEFAULT_APPLIED, "1")


def remove_sales_person_question():
	""" "Who handles this customer?" used to be a seeded question; it's now derived
	automatically from the session user's linked Sales Person instead (see
	``erpnext_customer._session_sales_person``), so it should never be asked. Clean
	up the row a site installed before this change shipped — a fresh install never
	creates it in the first place, since it's no longer in the fixture."""
	if frappe.db.exists("Customer Wizard Mapping", "sales_person"):
		frappe.delete_doc("Customer Wizard Mapping", "sales_person", ignore_permissions=True, force=True)
