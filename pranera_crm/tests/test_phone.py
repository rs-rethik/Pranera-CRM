import frappe
from crm.tests import CRMTestCase

from pranera_crm.phone import get_phone_picker_data, normalize_isd


class TestPhonePicker(CRMTestCase):
	def test_isd_is_reduced_to_plus_and_digits(self):
		self.assertEqual(normalize_isd("+1-684"), "+1684")
		self.assertEqual(normalize_isd("+91"), "+91")
		self.assertEqual(normalize_isd(""), "")
		self.assertEqual(normalize_isd(None), "")

	def test_crm_phone_fields_are_listed_by_label(self):
		labels = get_phone_picker_data()["labels"]
		self.assertIn("Mobile No.", labels)
		self.assertIn("Phone", labels)

	def test_countries_have_a_name_an_iso_code_and_a_dial_code(self):
		countries = get_phone_picker_data()["countries"]
		india = next(c for c in countries if c["code"] == "in")
		self.assertEqual(india["isd"], "+91")
		self.assertTrue(all(c["name"] and c["isd"].startswith("+") for c in countries))

	def test_default_country_follows_system_settings(self):
		frappe.db.set_single_value("System Settings", "country", "India")
		self.assertEqual(get_phone_picker_data()["default_country"], "in")
