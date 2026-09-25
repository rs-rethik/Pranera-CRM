import frappe
from crm.tests import CRMTestCase

from pranera_crm import setup


class TestEnsureTerritories(CRMTestCase):
	"""F11: the seeded "territory" question's secondary target is ERPNext's own
	Territory doctype, which only exists if the setup wizard's country was India."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_seeds_both_crm_and_erpnext_territory(self):
		frappe.db.delete("CRM Territory", {"name": ["in", ("India", "Rest Of The World")]})
		frappe.db.delete("Territory", {"name": ["in", ("India", "Rest Of The World")]})

		setup.ensure_territories()

		for name in ("India", "Rest Of The World"):
			self.assertTrue(frappe.db.exists("CRM Territory", name))
			self.assertTrue(frappe.db.exists("Territory", name))

	def test_idempotent_when_already_seeded(self):
		setup.ensure_territories()
		setup.ensure_territories()
		self.assertTrue(frappe.db.exists("Territory", "India"))


class TestEnsureCustomerWizardQuestions(CRMTestCase):
	"""F1: seed-once, never re-touching a row (whether unedited or admin-customised)
	that already exists — the whole point of moving this off the fixtures hook."""

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_running_twice_does_not_duplicate_or_error(self):
		setup.ensure_customer_wizard_questions()
		count_before = frappe.db.count("Customer Wizard Mapping")
		setup.ensure_customer_wizard_questions()
		self.assertEqual(frappe.db.count("Customer Wizard Mapping"), count_before)

	def test_admin_edit_survives_a_reseed(self):
		setup.ensure_customer_wizard_questions()
		name = frappe.db.get_value("Customer Wizard Mapping", {"question_key": "territory"}, "name")
		self.assertTrue(name)

		frappe.db.set_value("Customer Wizard Mapping", name, "enabled", 0)
		setup.ensure_customer_wizard_questions()
		self.assertEqual(frappe.db.get_value("Customer Wizard Mapping", name, "enabled"), 0)


class TestEnsureErpnextCustomerSyncDisabled(CRMTestCase):
	"""F2: pranera_crm's wizard is meant to be the only place a Customer gets
	created from a Deal — default CRM's own competing setting off, once, the same
	"never fight an admin's later choice" way `settings.ensure_default` does."""

	SETTINGS = "ERPNext CRM Settings"
	FIELD = "create_customer_on_status_change"

	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_disables_the_setting_by_default(self):
		frappe.db.set_default(setup.ERPNEXT_SYNC_DEFAULT_APPLIED, "")
		frappe.db.set_single_value(self.SETTINGS, self.FIELD, 1)

		setup.ensure_erpnext_customer_sync_disabled()

		self.assertEqual(frappe.db.get_single_value(self.SETTINGS, self.FIELD), 0)

	def test_never_overwrites_an_admins_later_choice(self):
		frappe.db.set_default(setup.ERPNEXT_SYNC_DEFAULT_APPLIED, "")
		setup.ensure_erpnext_customer_sync_disabled()

		frappe.db.set_single_value(self.SETTINGS, self.FIELD, 1)
		setup.ensure_erpnext_customer_sync_disabled()

		self.assertEqual(frappe.db.get_single_value(self.SETTINGS, self.FIELD), 1)


class TestCustomerGroupFollowsCustomerType(CRMTestCase):
	"""A Registered Business must never end up in the Individual customer group,
	nor an Individual in a business group."""

	def setUp(self):
		frappe.set_user("Administrator")
		setup.ensure_customer_wizard_questions()

	def tearDown(self):
		frappe.db.rollback()

	def _group(self, answers):
		from pranera_crm import customer_wizard as cw

		return cw.resolve("Organization", answers)["fields"]["Customer"].get("customer_group")

	def test_business_can_not_be_individual_group(self):
		self.assertEqual(
			self._group({"customer_type": "company", "customer_group": "business"}), "Commercial"
		)
		values = [o.option_value for o in frappe.get_doc("Customer Wizard Mapping", "customer_group").options]
		self.assertNotIn("individual", values)

	def test_individual_gets_individual_group_regardless_of_group_answer(self):
		self.assertEqual(self._group({"customer_type": "individual"}), "Individual")
		self.assertEqual(
			self._group({"customer_type": "individual", "customer_group": "government"}), "Individual"
		)

	def test_no_group_until_customer_type_answered(self):
		self.assertIsNone(self._group({}))


def _failing(name):
	def step():
		raise Exception("boom")

	step.__name__ = name
	return step


class TestHooksLogInsteadOfFailing(CRMTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_a_failing_step_is_logged_and_the_rest_still_run(self):
		from unittest.mock import patch

		with (
			patch.object(setup, "ensure_default", new=_failing("ensure_default")),
			patch.object(setup, "ensure_territories") as later_step,
			patch("frappe.log_error") as log_error,
		):
			setup.after_migrate()

		later_step.assert_called_once()
		log_error.assert_called_once()
		self.assertIn("ensure_default", log_error.call_args.kwargs["title"])

	def test_after_install_also_survives_a_failing_step(self):
		from unittest.mock import patch

		with (
			patch.object(
				setup, "ensure_payment_terms_template", new=_failing("ensure_payment_terms_template")
			),
			patch.object(setup, "remove_sales_person_question") as last_step,
			patch("frappe.log_error") as log_error,
		):
			setup.after_install()

		last_step.assert_called_once()
		log_error.assert_called_once()

	def test_before_migrate_logs_instead_of_raising(self):
		from unittest.mock import patch

		with (
			patch("frappe.db.exists", side_effect=Exception("db gone")),
			patch("frappe.log_error") as log_error,
		):
			setup.before_migrate()

		log_error.assert_called_once()

	def test_after_install_and_after_migrate_log_even_if_the_step_runner_breaks(self):
		from unittest.mock import patch

		for hook in (setup.after_install, setup.after_migrate):
			with (
				patch.object(setup, "_run_safely", side_effect=Exception("runner broke")),
				patch("frappe.log_error") as log_error,
			):
				hook()
			log_error.assert_called_once()
			self.assertIn(hook.__name__, log_error.call_args.kwargs["title"])
