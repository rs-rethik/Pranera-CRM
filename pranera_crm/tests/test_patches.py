from frappe.tests.utils import FrappeTestCase

from pranera_crm.patches.convert_override_roles_to_multiselect import roles_from_text


class TestOverrideRolesPatch(FrappeTestCase):
	def test_text_becomes_a_clean_ordered_role_list(self):
		self.assertEqual(
			roles_from_text("  System Manager \n\n Sales Manager \nSystem Manager"),
			["System Manager", "Sales Manager"],
		)

	def test_blank_means_no_roles(self):
		self.assertEqual(roles_from_text(None), [])
		self.assertEqual(roles_from_text(" \n "), [])
