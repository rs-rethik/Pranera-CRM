from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase

from pranera_crm import pincode as pc

# what India Post answers for Tiruppur's 641604: the old district, the town in Block
TIRUPPUR_POST = [
	{
		"Status": "Success",
		"PostOffice": [
			*[{"District": "Coimbatore", "Block": "Tiruppur", "State": "Tamil Nadu"}] * 5,
			{"District": "Coimbatore", "Block": "Tirupur", "State": "Tamil Nadu"},
		],
	}
]


def post_reply(body):
	response = MagicMock()
	response.json.return_value = body
	return response


class TestPincode(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for code in ("641604", "641999", "160017"):
			frappe.cache.delete_value(pc.CACHE_PREFIX + code)

	def address(self, city, pincode):
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": f"Pincode Test {city}",
				"address_line1": "1 Test Street",
				"city": city,
				"state": "Tamil Nadu",
				"country": "India",
				"pincode": pincode,
			}
		).insert(ignore_permissions=True)

	def test_state_from_india_compliance(self):
		self.assertEqual(pc.states_for_pincode("641604"), ["Tamil Nadu"])
		self.assertEqual(set(pc.states_for_pincode("160017")), {"Punjab", "Chandigarh"})

	def test_india_post_names_ranked_by_the_sites_own_usage(self):
		self.address("TIRUPUR, ", "641604")
		self.address("Tirupur", "641604")
		with patch.object(pc.requests, "get", return_value=post_reply(TIRUPPUR_POST)):
			info = pc.pincode_details("641604")
		self.assertEqual(info["state"], "Tamil Nadu")
		self.assertEqual(info["country"], "India")
		self.assertEqual(info["source"], "india_post")
		# the site writes "Tirupur": it comes first; India Post's stale district is still offered
		self.assertEqual(info["cities"][0], "Tirupur")
		self.assertIn("Coimbatore", info["cities"])

	def test_india_post_district_first_when_the_site_has_no_addresses(self):
		with patch.object(pc.requests, "get", return_value=post_reply(TIRUPPUR_POST)):
			cities = pc.pincode_details("641604")["cities"]
		self.assertEqual(cities, ["Coimbatore", "Tiruppur", "Tirupur"])

	def test_site_addresses_when_india_post_is_down(self):
		self.address("Tiruppur", "641999")
		with patch.object(pc.requests, "get", side_effect=requests.ConnectionError):
			info = pc.pincode_details("641999")
		self.assertEqual((info["cities"], info["source"]), (["Tiruppur"], "addresses"))
		# a failed call isn't cached: India Post is asked again next time
		self.assertIsNone(frappe.cache.get_value(pc.CACHE_PREFIX + "641999"))

	def test_india_post_is_asked_once_per_pincode(self):
		with patch.object(pc.requests, "get", return_value=post_reply(TIRUPPUR_POST)) as get:
			pc.pincode_details("641604")
			pc.pincode_details("641604")
		self.assertEqual(get.call_count, 1)

	def test_two_states_leave_the_state_to_pick(self):
		chandigarh = [
			{"Status": "Success", "PostOffice": [{"District": "Chandigarh", "State": "Chandigarh"}]}
		]
		with patch.object(pc.requests, "get", return_value=post_reply(chandigarh)):
			info = pc.pincode_details("160017")
		self.assertEqual(info["state"], "")
		self.assertEqual(info["cities"], ["Chandigarh"])

	def test_not_a_pincode(self):
		for bad in ("041604", "64160", "abcdef"):
			self.assertRaises(frappe.ValidationError, pc.pincode_details, bad)

	def test_needs_address_read_permission(self):
		frappe.set_user("Guest")
		self.assertRaises(frappe.PermissionError, pc.pincode_details, "641604")

	def test_states_list(self):
		states = pc.india_states()
		self.assertIn("Tamil Nadu", states)
		self.assertNotIn("Other Territory", states)
