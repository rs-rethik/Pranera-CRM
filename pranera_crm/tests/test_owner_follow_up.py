import json
from unittest.mock import patch

import frappe
from crm.tests import CRMTestCase
from frappe.utils import add_days, now_datetime
from frappe.utils.password import set_encrypted_password

from pranera_crm import owner_follow_up as ofu
from pranera_crm.tests.test_api import make_lead

REAL_SEND = ofu.send
OWNER = "zzf-owner@example.com"
TEMPLATE = "zzf_owner_follow_up-en"
BUTTON_TEMPLATE = "zzf_owner_follow_up_button-en"
ACCOUNT = "ZZF Meta"


def _user(email, mobile="9876543210", enabled=1):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Ravi",
				"send_welcome_email": 0,
				"roles": [{"role": "Sales User"}],
			}
		).insert(ignore_permissions=True)
	frappe.db.set_value("User", email, {"mobile_no": mobile, "enabled": enabled})


class TestOwnerFollowUp(CRMTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ofu.ensure_fields()

	def setUp(self):
		frappe.set_user("Administrator")
		for p in (patch.object(frappe.db, "commit"), patch.object(ofu, "send", side_effect=self._send)):
			p.start()
			self.addCleanup(p.stop)
		self.sent = []
		_user(OWNER)
		if not frappe.db.exists("WhatsApp Account", ACCOUNT):
			frappe.get_doc(
				{
					"doctype": "WhatsApp Account",
					"account_name": ACCOUNT,
					"status": "Active",
					"phone_id": "zzf",
				}
			).db_insert()
		set_encrypted_password("WhatsApp Account", ACCOUNT, "test-token", "token")
		if not frappe.db.exists("WhatsApp Templates", TEMPLATE):
			frappe.get_doc(
				{
					"doctype": "WhatsApp Templates",
					"name": TEMPLATE,
					"template_name": "zzf_owner_follow_up",
					"actual_name": "zzf_owner_follow_up",
					"language_code": "en",
					"template": "Hi {{1}}, {{2}} {{3}} idle {{4}} days: {{5}} thanks",
					"sample_values": "Ravi,Lead,Sri Ganesh Mills (CRM-LEAD-1),7,https://x/crm/leads/1",
					"category": "UTILITY",
				}
			).db_insert()
		frappe.db.set_single_value("WhatsApp Settings", "default_outgoing_account", ACCOUNT)
		for field, value in {
			"enable_owner_follow_up": 1,
			"owner_follow_up_days": 7,
			"owner_follow_up_daily_limit": 10,
			"owner_follow_up_template": TEMPLATE,
		}.items():
			frappe.db.set_single_value(ofu.SETTINGS, field, value)
		frappe.clear_document_cache(ofu.SETTINGS, ofu.SETTINGS)
		frappe.db.set_value("CRM Lead", {"name": ["is", "set"]}, "lead_owner", None, update_modified=False)
		frappe.db.set_value("CRM Deal", {"name": ["is", "set"]}, "deal_owner", None, update_modified=False)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _send(self, cfg, record, contact):
		self.sent.append((record.name, contact.number, contact.name, record.days))

	def _lead(self, idle_days=8, owner=OWNER, status=None):
		lead = make_lead(lead_owner=owner)
		values = {"modified": add_days(now_datetime(), -idle_days)}
		if status:
			values["status"] = status
		frappe.db.set_value("CRM Lead", lead.name, values, update_modified=False)
		return lead.name

	def test_an_idle_lead_messages_its_owner_once_a_week(self):
		lead = self._lead()
		self.assertEqual(ofu.run(), [("CRM Lead", lead)])
		self.assertEqual(self.sent, [(lead, "919876543210", "Ravi", 8)])
		self.assertEqual(ofu.run(), [])
		frappe.db.set_value(
			"CRM Lead", lead, ofu.SENT_FIELD, add_days(now_datetime(), -8), update_modified=False
		)
		self.assertEqual(ofu.run(), [("CRM Lead", lead)])

	def test_recent_activity_holds_it_back(self):
		lead = self._lead()
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Comment",
				"reference_doctype": "CRM Lead",
				"reference_name": lead,
				"content": "Spoke to the buyer",
			}
		).insert(ignore_permissions=True)
		fresh = self._lead(idle_days=3)
		self.assertEqual(ofu.run(), [])
		self.assertTrue(lead and fresh)

	def test_closed_records_and_owners_without_a_number_are_left_out(self):
		lost = frappe.db.get_value("CRM Lead Status", {"type": "Lost"})
		if lost:
			frappe.db.set_value(
				"CRM Lead", self._lead(), {"status": lost, "lost_reason": None}, update_modified=False
			)
		_user("zzf-nophone@example.com", mobile="")
		self._lead(owner="zzf-nophone@example.com")
		_user("zzf-disabled@example.com", mobile="9876500002", enabled=0)
		self._lead(owner="zzf-disabled@example.com")
		self.assertEqual(ofu.run(), [])

	def test_the_daily_limit_sends_the_longest_idle_first(self):
		frappe.db.set_single_value(ofu.SETTINGS, "owner_follow_up_daily_limit", 2)
		frappe.clear_document_cache(ofu.SETTINGS, ofu.SETTINGS)
		oldest, middle = self._lead(idle_days=30), self._lead(idle_days=20)
		self._lead(idle_days=10)
		self.assertEqual([name for _, name in ofu.run()], [oldest, middle])

	def test_nothing_without_the_switch_an_account_or_a_five_value_template(self):
		self._lead()
		frappe.db.set_single_value(ofu.SETTINGS, "enable_owner_follow_up", 0)
		frappe.clear_document_cache(ofu.SETTINGS, ofu.SETTINGS)
		self.assertEqual(ofu.run(), [])
		frappe.db.set_single_value(ofu.SETTINGS, "enable_owner_follow_up", 1)
		frappe.clear_document_cache(ofu.SETTINGS, ofu.SETTINGS)
		frappe.db.set_value("WhatsApp Templates", TEMPLATE, "sample_values", "Ravi,Lead")
		self.assertEqual(ofu.run(), [])
		self.assertEqual(self.sent, [])

	def test_numbers_get_the_country_code(self):
		frappe.db.set_single_value("System Settings", "country", "India")
		self.assertEqual(ofu.whatsapp_number("98765 43210"), "919876543210")
		self.assertEqual(ofu.whatsapp_number("+91 98765-43210"), "919876543210")
		self.assertEqual(ofu.whatsapp_number("12345"), None)

	def _real_send(self, template=TEMPLATE):
		lead = self._lead()
		frappe.db.set_single_value(ofu.SETTINGS, "owner_follow_up_template", template)
		frappe.clear_document_cache(ofu.SETTINGS, ofu.SETTINGS)
		record = ofu.idle_records("CRM Lead", add_days(now_datetime(), -7))[0]
		requests = []

		def post(url, headers, data):
			requests.append(json.loads(data))
			return {"messages": [{"id": "wamid.TEST"}]}

		with patch.object(ofu, "make_post_request", post):
			REAL_SEND(ofu.config(), record, ofu.owner_contact(OWNER))
		return lead, requests[0]

	def test_the_message_goes_from_the_settings_account_with_the_link_in_the_text(self):
		lead, data = self._real_send()
		self.assertEqual(data["to"], "919876543210")
		self.assertEqual(data["template"]["name"], "zzf_owner_follow_up")
		self.assertEqual(len(data["template"]["components"]), 1)
		params = [p["text"] for p in data["template"]["components"][0]["parameters"]]
		self.assertEqual(params[:2], ["Ravi", "Lead"])
		self.assertIn(lead, params[2])
		self.assertEqual(params[3], "8")
		self.assertTrue(params[4].endswith(f"/crm/leads/{lead}"))
		saved = frappe.get_all(
			"WhatsApp Message",
			filters={"message_id": "wamid.TEST"},
			fields=["to", "whatsapp_account", "reference_doctype", "message"],
		)
		self.assertEqual(len(saved), 1)
		self.assertEqual((saved[0].whatsapp_account, saved[0].reference_doctype), (ACCOUNT, None))
		self.assertIn(f"idle 8 days: {params[4]}", saved[0].message)

	def test_a_button_template_opens_the_record_from_the_button(self):
		if not frappe.db.exists("WhatsApp Templates", BUTTON_TEMPLATE):
			frappe.get_doc(
				{
					"doctype": "WhatsApp Templates",
					"name": BUTTON_TEMPLATE,
					"template_name": "zzf_owner_follow_up_button",
					"actual_name": "zzf_owner_follow_up_button",
					"language_code": "en",
					"template": "Hi {{1}}, {{2}} {{3}} idle {{4}} days. Thanks",
					"sample_values": "Ravi,Lead,Sri Ganesh Mills (CRM-LEAD-1),7",
					"category": "UTILITY",
				}
			).db_insert()
			frappe.get_doc(
				{
					"doctype": "WhatsApp Button",
					"parent": BUTTON_TEMPLATE,
					"parenttype": "WhatsApp Templates",
					"parentfield": "buttons",
					"idx": 1,
					"button_type": "Visit Website",
					"button_label": "Open in CRM",
					"url_type": "Dynamic",
					"website_url": "https://crm.example.com/crm-open/{{1}}",
				}
			).db_insert()
		lead, data = self._real_send(BUTTON_TEMPLATE)
		body, button = data["template"]["components"]
		self.assertEqual(len(body["parameters"]), 4)
		self.assertEqual(
			button,
			{
				"type": "button",
				"sub_type": "url",
				"index": "0",
				"parameters": [{"type": "text", "text": lead}],
			},
		)

	def test_crm_open_goes_to_the_lead_or_deal(self):
		from pranera_crm.www import crm_open

		lead = self._lead()
		for user, expected in (("Administrator", f"/crm/leads/{lead}"), ("Guest", "/login?redirect-to=")):
			frappe.set_user(user)
			frappe.form_dict.name = lead
			with self.assertRaises(frappe.Redirect):
				crm_open.get_context(frappe._dict())
			self.assertTrue(frappe.local.flags.redirect_location.startswith(expected))
		frappe.set_user("Administrator")

	def test_unset_days_and_limit_fall_back_to_the_defaults(self):
		frappe.db.set_single_value(ofu.SETTINGS, "owner_follow_up_days", 0)
		frappe.db.set_single_value(ofu.SETTINGS, "owner_follow_up_daily_limit", 0)
		frappe.clear_document_cache(ofu.SETTINGS, ofu.SETTINGS)
		cfg = ofu.config()
		self.assertEqual((cfg.days, cfg.limit), (ofu.DEFAULT_DAYS, ofu.DEFAULT_DAILY_LIMIT))
		for _ in range(ofu.DEFAULT_DAILY_LIMIT + 2):
			self._lead()
		self.assertEqual(len(ofu.run()), ofu.DEFAULT_DAILY_LIMIT)
