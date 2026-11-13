from datetime import date, datetime
from unittest.mock import patch

import frappe
from crm.tests import CRMTestCase

from pranera_crm import conversion_report as cr

TEMPLATE = "zzc_conversion_report-en"


def make_lead(**kwargs):
	suffix = frappe.generate_hash(length=8)
	return frappe.get_doc(
		{
			"doctype": "CRM Lead",
			"first_name": "Report",
			"last_name": suffix,
			"email": f"report-{suffix}@example.com",
			**kwargs,
		}
	).insert(ignore_permissions=True)


DAY = "2031-03-05"  # a Wednesday, far from real data


def _template(header_type="DOCUMENT", sample_values="1 Mar,10,2,20%"):
	if frappe.db.exists("WhatsApp Templates", TEMPLATE):
		frappe.db.set_value(
			"WhatsApp Templates", TEMPLATE, {"header_type": header_type, "sample_values": sample_values}
		)
		return
	doc = frappe.get_doc(
		{
			"doctype": "WhatsApp Templates",
			"name": TEMPLATE,
			"template_name": "zzc_conversion_report",
			"actual_name": "zzc_conversion_report",
			"template": "Report {{1}}: {{2}} leads, {{3}} converted ({{4}}).",
			"language_code": "en",
			"header_type": header_type,
			"status": "APPROVED",
			"sample_values": sample_values,
			"category": "UTILITY",
		}
	)
	doc.db_insert()


class TestPeriods(CRMTestCase):
	def test_presets(self):
		ref = date(2031, 3, 5)  # Wednesday
		self.assertEqual(cr.period("yesterday", ref), (date(2031, 3, 4), date(2031, 3, 4)))
		self.assertEqual(cr.period("last_7_days", ref), (date(2031, 2, 26), date(2031, 3, 4)))
		self.assertEqual(cr.period("last_week", ref), (date(2031, 2, 24), date(2031, 3, 2)))
		self.assertEqual(cr.period("this_month", ref), (date(2031, 3, 1), date(2031, 3, 5)))
		self.assertEqual(cr.period("last_month", ref), (date(2031, 2, 1), date(2031, 2, 28)))
		self.assertEqual(cr.scheduled_period("Weekly", ref), cr.period("last_week", ref))
		self.assertEqual(cr.period_label("2031-03-01", "2031-03-07"), "1 Mar to 7 Mar 2031")

	def test_is_due(self):
		cfg = frappe._dict(
			enabled=1,
			template=TEMPLATE,
			recipients=[frappe._dict(enabled=1)],
			frequency="Weekly",
			weekday="Wednesday",
			send_time="09:00:00",
			month_day=1,
			last_sent_on=None,
		)
		self.assertFalse(cr.is_due(cfg, datetime(2031, 3, 5, 8, 59)))  # before the time
		self.assertTrue(cr.is_due(cfg, datetime(2031, 3, 5, 9, 0)))
		self.assertFalse(cr.is_due(cfg, datetime(2031, 3, 6, 9, 0)))  # Thursday
		cfg.last_sent_on = "2031-03-05 09:00:00"
		self.assertFalse(cr.is_due(cfg, datetime(2031, 3, 5, 12, 0)))  # already sent today
		cfg.update(last_sent_on=None, frequency="Monthly", month_day=5)
		self.assertTrue(cr.is_due(cfg, datetime(2031, 3, 5, 10, 0)))
		cfg.update(frequency="Daily", enabled=0)
		self.assertFalse(cr.is_due(cfg, datetime(2031, 3, 5, 10, 0)))


class TestReport(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.root = self._territory("ZZC All")
		self.region = self._territory("ZZC Region", self.root)
		self.city = self._territory("ZZC City", self.region)
		self.leads = [make_lead(territory=self.city) for _ in range(3)] + [make_lead()]
		for lead in self.leads:
			frappe.db.set_value("CRM Lead", lead.name, "creation", f"{DAY} 10:00:00", update_modified=False)
		frappe.db.set_value("CRM Lead", self.leads[0].name, "converted", 1)
		frappe.db.set_value("CRM Lead", self.leads[3].name, "territory", None, update_modified=False)
		for lead in self.leads:
			self.addCleanup(frappe.delete_doc, "CRM Lead", lead.name, force=True, ignore_permissions=True)

	def _territory(self, name, parent=None):
		if not frappe.db.exists("CRM Territory", name):
			frappe.get_doc(
				{
					"doctype": "CRM Territory",
					"territory_name": name,
					"parent_crm_territory": parent,
					"is_group": 1,
				}
			).insert(ignore_permissions=True)
		return name

	def test_counts_and_groups(self):
		data = cr.build(DAY, DAY)
		self.assertEqual((data["summary"]["leads"], data["summary"]["converted"]), (4, 1))
		self.assertEqual(data["summary"]["rate"], 25.0)
		city = next(r for r in data["territories"] if r["name"] == self.city)
		self.assertEqual((city["leads"], city["converted"], city["parent"]), (3, 1, self.region))
		self.assertTrue(any(r["name"] == cr.NO_TERRITORY for r in data["territories"]))
		self.assertEqual(sum(r["leads"] for r in data["people"]), 4)

		pdf = cr.render_pdf(data)
		self.assertTrue(pdf.startswith(b"%PDF"))
		html = cr.render_html(data)
		for text in ("Sales person wise", "Territory wise", self.region, self.city):
			self.assertIn(text, html)

	def test_leads_not_converted(self):
		status = frappe.db.get_value("CRM Lead", self.leads[1].name, "status")
		data = cr.build(DAY, DAY)
		pending = data["pending"]
		# 4 new leads, 1 converted: the other 3 are listed with their status and sales person
		self.assertEqual(pending["total"], 3)
		self.assertEqual(
			sorted(r["name"] for r in pending["leads"]), sorted(lead.name for lead in self.leads[1:])
		)
		self.assertNotIn(self.leads[0].name, [r["name"] for r in pending["leads"]])
		self.assertEqual(sum(r["leads"] for r in pending["by_status"]), 3)
		self.assertIn(status, [r["name"] for r in pending["by_status"]])
		self.assertEqual(sum(r["total"] for r in pending["people"]), 3)
		self.assertEqual(pending["more"], 0)
		self.assertIn("<h2>Leads not converted</h2>", cr.render_html(data))

	def test_long_lead_list_is_cut(self):
		with patch.object(cr, "PENDING_LIMIT", 2):
			pending = cr.build(DAY, DAY)["pending"]
		self.assertEqual((len(pending["leads"]), pending["more"]), (2, 1))

	def test_no_section_when_all_converted(self):
		for lead in self.leads:
			frappe.db.set_value("CRM Lead", lead.name, "converted", 1)
		data = cr.build(DAY, DAY)
		self.assertEqual(data["pending"]["total"], 0)
		self.assertNotIn("<h2>Leads not converted</h2>", cr.render_html(data))

	def test_send_uploads_once_and_sends_to_each_recipient(self):
		_template()
		cfg = frappe.get_single(cr.SETTINGS)
		cfg.whatsapp_account = None
		cfg.template = TEMPLATE
		cfg.set(
			"recipients",
			[
				{"recipient_name": "Head", "whatsapp_number": "9876543210", "enabled": 1},
				{"recipient_name": "Paused", "whatsapp_number": "9876500000", "enabled": 0},
				{"recipient_name": "No number", "enabled": 1},
			],
		)
		cfg.save()
		sent = []
		with (
			patch.object(cr, "account_name", return_value="ZZC Meta"),
			patch.object(cr, "upload_to_meta", return_value="MEDIA-1") as upload,
			patch(
				"pranera_crm.owner_follow_up.post_to_meta",
				side_effect=lambda account, data: sent.append(data) or "wamid.zzc",
			),
		):
			out = cr.send(DAY, DAY)
		upload.assert_called_once()
		self.assertEqual([r["status"] for r in out["results"]], ["Sent", "Skipped"])
		self.assertEqual(len(sent), 1)
		header, body = sent[0]["template"]["components"]
		self.assertEqual(header["parameters"][0]["document"]["id"], "MEDIA-1")
		self.assertEqual([p["text"] for p in body["parameters"]], ["5 Mar 2031", "4", "1", "25%"])
		self.assertTrue(sent[0]["to"].endswith("9876543210"))
		logged = frappe.get_all(
			"WhatsApp Message", filters={"message_id": "wamid.zzc"}, fields=["content_type", "message"]
		)
		self.assertEqual(logged[0].content_type, "document")
		self.assertIn("4 leads, 1 converted (25%)", logged[0].message)

	def test_template_needs_a_document_header(self):
		_template(header_type="")
		cfg = frappe.get_single(cr.SETTINGS)
		cfg.template = TEMPLATE
		self.assertRaises(frappe.ValidationError, cfg.save)
		_template()
