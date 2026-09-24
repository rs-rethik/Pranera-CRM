from unittest.mock import patch

import frappe

from crm.tests import CRMTestCase
from pranera_crm import email_verification as ev
from pranera_crm.api import convert
from pranera_crm.tests.test_api import deal_status, make_contact, make_lead, make_user


def _lead_without_verification():
	lead = make_lead()
	frappe.cache.delete_value(ev._key("verified", lead.name, lead.email))
	return lead


def _capture_code(lead, email):
	sent = {}

	def fake_sendmail(**kwargs):
		sent.update(kwargs)

	with patch("frappe.sendmail", fake_sendmail):
		result = ev.send_email_otp(lead, email)
	state = frappe.cache.get_value(ev._key("otp", lead, email), expires=True)
	import pyotp

	return result, sent, pyotp.HOTP(state["secret"]).at(state["counter"])


class TestEmailVerification(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.lead = _lead_without_verification()
		self.email = self.lead.email

	def tearDown(self):
		frappe.set_user("Administrator")
		for kind in ("otp", "verified"):
			frappe.cache.delete_value(ev._key(kind, self.lead.name, self.email))
		frappe.db.rollback()

	def test_send_emails_the_code_and_never_returns_it(self):
		result, sent, code = _capture_code(self.lead.name, self.email)
		self.assertEqual(result, {"sent": True})
		self.assertEqual(sent["recipients"], self.email)
		self.assertIn(code, sent["message"])

	def test_correct_code_verifies(self):
		_, _, code = _capture_code(self.lead.name, self.email)
		self.assertFalse(ev.is_email_verified(self.lead.name, self.email))
		self.assertEqual(ev.verify_email_otp(self.lead.name, self.email, code), {"verified": True})
		self.assertTrue(ev.is_email_verified(self.lead.name, self.email.upper()))

	def test_wrong_code_fails_and_five_wrong_codes_invalidate(self):
		_, _, code = _capture_code(self.lead.name, self.email)
		wrong = "000000" if code != "000000" else "111111"
		for _i in range(ev.MAX_ATTEMPTS):
			with self.assertRaises(frappe.ValidationError):
				ev.verify_email_otp(self.lead.name, self.email, wrong)
		with self.assertRaises(frappe.ValidationError):
			ev.verify_email_otp(self.lead.name, self.email, code)
		self.assertFalse(ev.is_email_verified(self.lead.name, self.email))

	def test_no_code_requested_fails(self):
		with self.assertRaises(frappe.ValidationError):
			ev.verify_email_otp(self.lead.name, self.email, "123456")

	def test_verification_is_per_email(self):
		_, _, code = _capture_code(self.lead.name, self.email)
		ev.verify_email_otp(self.lead.name, self.email, code)
		self.assertFalse(ev.is_email_verified(self.lead.name, "someone-else@example.com"))

	def test_resend_invalidates_the_previous_verification(self):
		_, _, code = _capture_code(self.lead.name, self.email)
		ev.verify_email_otp(self.lead.name, self.email, code)
		_capture_code(self.lead.name, self.email)
		self.assertFalse(ev.is_email_verified(self.lead.name, self.email))

	def test_invalid_email_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			ev.send_email_otp(self.lead.name, "not-an-email")

	def test_permission_denied_without_lead_write(self):
		frappe.set_user(make_user(roles=[], prefix="cw-ev-noperm"))
		with self.assertRaises(frappe.PermissionError):
			ev.send_email_otp(self.lead.name, self.email)

	def test_mail_failure_is_reported(self):
		with patch("frappe.sendmail", side_effect=Exception("smtp down")):
			with self.assertRaises(frappe.ValidationError):
				ev.send_email_otp(self.lead.name, self.email)
		self.assertIsNone(frappe.cache.get_value(ev._key("otp", self.lead.name, self.email), expires=True))


class TestConvertRequiresVerifiedEmail(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.deal = {"status": deal_status()}

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_unverified_new_contact_email_blocks_convert(self):
		lead = _lead_without_verification()
		with self.assertRaises(ev.EmailNotVerified):
			convert(lead.name, deal=self.deal)
		lead.reload()
		self.assertFalse(lead.converted)

	def test_edited_email_must_be_verified_not_the_original(self):
		lead = make_lead()
		with self.assertRaises(ev.EmailNotVerified):
			convert(lead.name, deal=self.deal, lead_updates={"email": "changed@example.com"})

	def test_verified_email_converts(self):
		lead = make_lead()
		self.assertTrue(convert(lead.name, deal=self.deal)["deal"])

	def test_existing_contact_skips_verification(self):
		lead = _lead_without_verification()
		contact = make_contact()
		self.assertTrue(convert(lead.name, deal=self.deal, existing_contact=contact.name)["deal"])

	def test_blank_email_is_allowed(self):
		lead = _lead_without_verification()
		self.assertTrue(convert(lead.name, deal=self.deal, lead_updates={"email": ""})["deal"])
