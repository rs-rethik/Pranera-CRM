from unittest.mock import patch

import frappe
from crm.tests import CRMTestCase
from frappe.utils import add_days, now_datetime

from pranera_crm import follow_ups
from pranera_crm.tests.test_api import make_lead

LEAD_STATUSES = {
	"ZZF Awaiting Buyer": ("Buyer", 7),
	"ZZF Our Move": ("Us", 0),
	"ZZF Slow Buyer": ("Buyer", 30),
}


class TestFollowUps(CRMTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		follow_ups.ensure_fields()

	def setUp(self):
		frappe.set_user("Administrator")
		committing = patch.object(frappe.db, "commit")
		committing.start()
		self.addCleanup(committing.stop)
		for status, (waiting_on, days) in LEAD_STATUSES.items():
			if not frappe.db.exists("CRM Lead Status", status):
				frappe.get_doc(
					{
						"doctype": "CRM Lead Status",
						"lead_status": status,
						"type": "Ongoing",
						"waiting_on": waiting_on,
						"follow_up_after_days": days,
					}
				).insert()
		frappe.db.set_value("CRM Lead Status", {"name": ["not in", list(LEAD_STATUSES)]}, "waiting_on", "")
		frappe.db.set_value("CRM Deal Status", {"name": ["is", "set"]}, "waiting_on", "")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _lead(self, status="ZZF Awaiting Buyer", idle_days=8, owner="Administrator"):
		lead = make_lead(lead_owner=owner)
		frappe.db.set_value(
			"CRM Lead",
			lead.name,
			{"status": status, "modified": add_days(now_datetime(), -idle_days)},
			update_modified=False,
		)
		return lead.name

	def _tasks(self, lead):
		return frappe.get_all(
			"CRM Task",
			filters={"reference_doctype": "CRM Lead", "reference_docname": lead, "auto_follow_up": 1},
			fields=["assigned_to", "status", "title"],
		)

	def test_an_idle_buyer_status_gets_a_task_for_the_owner(self):
		lead = self._lead()
		follow_ups.create()
		tasks = self._tasks(lead)
		self.assertEqual(len(tasks), 1)
		self.assertEqual((tasks[0].assigned_to, tasks[0].status), ("Administrator", "Todo"))
		self.assertIn("7 days", tasks[0].title)

	def test_only_one_open_task_at_a_time(self):
		lead = self._lead()
		follow_ups.create()
		frappe.db.set_value("CRM Lead", lead, "modified", add_days(now_datetime(), -8), update_modified=False)
		frappe.db.set_value(
			"CRM Task",
			{"reference_docname": lead},
			"modified",
			add_days(now_datetime(), -8),
			update_modified=False,
		)
		follow_ups.create()
		self.assertEqual(len(self._tasks(lead)), 1)

	def test_recent_activity_or_a_recent_change_means_no_task(self):
		commented = self._lead()
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "CRM Lead",
				"reference_name": commented,
				"content": "Called, will send PO",
			}
		).insert(ignore_permissions=True)
		recent = self._lead(idle_days=3)
		follow_ups.create()
		self.assertEqual(self._tasks(commented), [])
		self.assertEqual(self._tasks(recent), [])

	def test_us_statuses_their_own_days_and_no_owner(self):
		ours = self._lead(status="ZZF Our Move", idle_days=40)
		slow = self._lead(status="ZZF Slow Buyer", idle_days=10)
		ownerless = self._lead(owner=None)
		follow_ups.create()
		self.assertEqual(self._tasks(ours), [])
		self.assertEqual(self._tasks(slow), [])
		self.assertEqual(self._tasks(ownerless), [])
		frappe.db.set_value(
			"CRM Lead", slow, "modified", add_days(now_datetime(), -31), update_modified=False
		)
		follow_ups.create()
		self.assertEqual(len(self._tasks(slow)), 1)
