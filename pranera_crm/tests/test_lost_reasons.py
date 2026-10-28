from types import SimpleNamespace

import frappe
from crm.tests import CRMTestCase

from pranera_crm import lost_reasons

LEAD_STATUSES = {"ZZT Unsuitable": "Lost", "ZZT Junk": "Lost", "ZZT Silent": "On Hold"}
REASONS = {
	"ZZT Deal Price": ("Deal", None),
	"ZZT Shared Range": ("Both", "ZZT Unsuitable"),
	"ZZT Anything": ("Both", None),
	"ZZT Below MOQ": ("Lead", "ZZT Unsuitable"),
	"ZZT Spam": ("Lead", "ZZT Junk"),
	"ZZT No Reply": ("Lead", "ZZT Silent"),
}


def make_lead():
	suffix = frappe.generate_hash(length=8)
	return frappe.get_doc(
		{
			"doctype": "CRM Lead",
			"first_name": "Lost",
			"last_name": suffix,
			"email": f"lost-{suffix}@example.com",
		}
	).insert()


def reasons_listed(referer=None, reference_doctype=None, txt="ZZT "):
	frappe.local.request = SimpleNamespace(headers={"Referer": referer} if referer else {})
	try:
		rows = lost_reasons.search(
			"CRM Lost Reason", txt, "name", 0, 100, [], reference_doctype=reference_doctype
		)
	finally:
		del frappe.local.request
	return {row[0] for row in rows}


class TestLostReasons(CRMTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		lost_reasons.ensure_fields()

	def setUp(self):
		frappe.set_user("Administrator")
		for status, status_type in LEAD_STATUSES.items():
			if not frappe.db.exists("CRM Lead Status", status):
				frappe.get_doc(
					{"doctype": "CRM Lead Status", "lead_status": status, "type": status_type}
				).insert()
		for reason, (applies_to, lead_status) in REASONS.items():
			if not frappe.db.exists("CRM Lost Reason", reason):
				frappe.get_doc(
					{
						"doctype": "CRM Lost Reason",
						"lost_reason": reason,
						"applies_to": applies_to,
						"lead_status": lead_status,
					}
				).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _close(self, lead, status, reason=None):
		lead.reload()
		lead.status = status
		lead.lost_reason = reason
		lead.lost_notes = "notes"
		lead.save()
		return lead

	def test_the_picker_on_a_lead_lists_lead_reasons_only(self):
		self.assertEqual(
			reasons_listed("https://crm.example.com/crm/leads/CRM-LEAD-2026-00001"),
			{"ZZT Shared Range", "ZZT Anything", "ZZT Below MOQ", "ZZT Spam", "ZZT No Reply"},
		)

	def test_the_picker_on_a_deal_lists_deal_reasons_only(self):
		self.assertEqual(
			reasons_listed("https://crm.example.com/crm/deals/CRM-DEAL-2026-00001"),
			{"ZZT Deal Price", "ZZT Shared Range", "ZZT Anything"},
		)

	def test_the_picker_elsewhere_lists_every_reason_and_untagged_ones_everywhere(self):
		frappe.db.set_value("CRM Lost Reason", "ZZT Anything", "applies_to", None)
		self.assertEqual(reasons_listed("https://crm.example.com/app/crm-lost-reason"), set(REASONS))
		self.assertIn("ZZT Anything", reasons_listed("https://crm.example.com/crm/deals/X"))

	def test_the_picker_takes_the_reference_doctype_first_and_searches_text(self):
		self.assertNotIn("ZZT Spam", reasons_listed(reference_doctype="CRM Deal"))
		self.assertEqual(reasons_listed("/crm/leads/X", txt="ZZT spa"), {"ZZT Spam"})

	def test_a_lead_cannot_take_a_deal_reason(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Deal reason"):
			self._close(make_lead(), "ZZT Unsuitable", "ZZT Deal Price")

	def test_a_lead_reason_must_belong_to_its_status(self):
		lead = make_lead()
		with self.assertRaisesRegex(frappe.ValidationError, "reason for 'ZZT Junk' leads"):
			self._close(lead, "ZZT Unsuitable", "ZZT Spam")
		self._close(lead, "ZZT Junk", "ZZT Spam")
		self._close(lead, "ZZT Unsuitable", "ZZT Shared Range")
		self._close(lead, "ZZT Unsuitable", "ZZT Anything")

	def test_a_status_with_one_reason_gets_it_filled_in(self):
		self.assertEqual(self._close(make_lead(), "ZZT Silent").lost_reason, "ZZT No Reply")
		self.assertIsNone(lost_reasons.only_reason("ZZT Unsuitable"))

	def test_a_reason_given_before_these_rules_is_not_checked_again(self):
		lead = make_lead()
		frappe.db.set_value(
			"CRM Lead", lead.name, {"status": "ZZT Unsuitable", "lost_reason": "ZZT Deal Price"}
		)
		lead.reload()
		lead.first_name = "Renamed"
		lead.save()
		self.assertEqual(lead.lost_reason, "ZZT Deal Price")

	def test_a_deal_cannot_take_a_lead_reason(self):
		lost = frappe.db.get_value("CRM Deal Status", {"type": "Lost"})
		deal = frappe.get_doc(
			{"doctype": "CRM Deal", "status": lost, "lost_reason": "ZZT Spam", "lost_notes": "notes"}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Lead reason"):
			deal.insert()
		deal.lost_reason = "ZZT Deal Price"
		deal.insert()
