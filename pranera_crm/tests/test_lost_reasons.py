from types import SimpleNamespace

import frappe
from crm.tests import CRMTestCase

from pranera_crm import lost_reasons
from pranera_crm.tests.test_api import make_lead

LEAD_STATUSES = {"Not Suitable": "Lost", "Junk": "Lost", "No Response": "On Hold"}


def reasons_listed(referer=None, reference_doctype=None, txt=""):
	frappe.local.request = SimpleNamespace(headers={"Referer": referer} if referer else {})
	try:
		rows = lost_reasons.search(
			"CRM Lost Reason", txt, "name", 0, 100, [], reference_doctype=reference_doctype
		)
	finally:
		del frappe.local.request
	return {row[0] for row in rows}


class TestLostReasons(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for status, status_type in LEAD_STATUSES.items():
			if not frappe.db.exists("CRM Lead Status", status):
				frappe.get_doc(
					{"doctype": "CRM Lead Status", "lead_status": status, "type": status_type}
				).insert()
			else:
				frappe.db.set_value("CRM Lead Status", status, "type", status_type)
		frappe.clear_cache(doctype="CRM Lead Status")
		lost_reasons.seed()

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

	def test_the_agreed_reasons_are_tagged(self):
		self.assertEqual(
			frappe.db.get_value("CRM Lost Reason", "Payment Terms Not Agreed", "applies_to"), "Deal"
		)
		self.assertEqual(
			frappe.db.get_value("CRM Lost Reason", "Spam", ["applies_to", "lead_status"]), ("Lead", "Junk")
		)
		self.assertEqual(frappe.db.get_value("CRM Lost Reason", "Other", "applies_to"), "Both")

	def test_the_seed_keeps_a_reasons_description(self):
		frappe.db.set_value("CRM Lost Reason", "Spam", "description", "edited")
		lost_reasons.seed()
		self.assertEqual(frappe.db.get_value("CRM Lost Reason", "Spam", "description"), "edited")

	def test_the_picker_on_a_lead_lists_lead_reasons_only(self):
		listed = reasons_listed("https://crm.example.com/crm/leads/CRM-LEAD-2026-00001")
		self.assertIn("Spam", listed)
		self.assertIn("Not in Our Range", listed)
		self.assertIn("Other", listed)
		self.assertNotIn("Payment Terms Not Agreed", listed)

	def test_the_picker_on_a_deal_lists_deal_reasons_only(self):
		listed = reasons_listed("https://crm.example.com/crm/deals/CRM-DEAL-2026-00001")
		self.assertIn("Payment Terms Not Agreed", listed)
		self.assertIn("Not in Our Range", listed)
		self.assertNotIn("Spam", listed)
		self.assertNotIn("Below MOQ", listed)

	def test_the_picker_elsewhere_lists_every_reason_and_untagged_ones(self):
		frappe.get_doc({"doctype": "CRM Lost Reason", "lost_reason": "Untagged Test Reason"}).insert()
		frappe.db.set_value("CRM Lost Reason", "Untagged Test Reason", "applies_to", None)
		listed = reasons_listed("https://crm.example.com/app/crm-lost-reason")
		self.assertTrue({"Spam", "Payment Terms Not Agreed", "Untagged Test Reason"} <= listed)
		self.assertIn("Untagged Test Reason", reasons_listed("https://crm.example.com/crm/deals/X"))

	def test_the_picker_takes_the_reference_doctype_first_and_searches_text(self):
		self.assertNotIn("Spam", reasons_listed(reference_doctype="CRM Deal"))
		self.assertEqual(reasons_listed("/crm/leads/X", txt="spa"), {"Spam"})

	def test_a_lead_cannot_take_a_deal_reason(self):
		lead = make_lead()
		with self.assertRaisesRegex(frappe.ValidationError, "Deal reason"):
			self._close(lead, "Not Suitable", "Payment Terms Not Agreed")

	def test_a_lead_reason_must_belong_to_its_status(self):
		lead = make_lead()
		with self.assertRaisesRegex(frappe.ValidationError, "reason for 'Junk' leads"):
			self._close(lead, "Not Suitable", "Spam")
		self._close(lead, "Junk", "Spam")
		self._close(lead, "Not Suitable", "Not in Our Range")
		self._close(lead, "Not Suitable", "Other")

	def test_no_response_gets_its_only_reason(self):
		lead = self._close(make_lead(), "No Response")
		self.assertEqual(lead.lost_reason, "No reply after 3 attempts")

	def test_an_open_lead_or_an_old_reason_is_not_checked(self):
		lead = make_lead()
		frappe.db.set_value(
			"CRM Lead", lead.name, {"status": "Not Suitable", "lost_reason": "Price Not Okay"}
		)
		lead.reload()
		lead.first_name = "Renamed"
		lead.save()  # closed before these rules: keeps its reason
		self.assertEqual(lead.lost_reason, "Price Not Okay")

	def test_a_deal_cannot_take_a_lead_reason(self):
		lost = frappe.db.get_value("CRM Deal Status", {"type": "Lost"})
		deal = frappe.get_doc(
			{"doctype": "CRM Deal", "status": lost, "lost_reason": "Spam", "lost_notes": "notes"}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "Lead reason"):
			deal.insert()
		deal.lost_reason = "Price Not Okay"
		deal.insert()
