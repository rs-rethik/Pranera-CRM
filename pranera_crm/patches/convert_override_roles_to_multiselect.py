import frappe

MAPPING = "Customer Wizard Mapping"


def roles_from_text(text: str | None) -> list[str]:
	"""The old one-role-per-line text, de-duplicated, in order."""
	roles = []
	for line in (text or "").splitlines():
		role = line.strip()
		if role and role not in roles:
			roles.append(role)
	return roles


def execute():
	"""Override Allowed For Roles used to be a text field with one role per line;
	it is now a multiselect table. Copy the old text (left behind in the table's
	old column) into rows for sites configured before that change."""
	if not frappe.db.has_column(MAPPING, "override_roles"):
		return

	old_rows = frappe.db.sql(
		f"select name, override_roles from `tab{MAPPING}` where ifnull(override_roles, '') != ''",
		as_dict=True,
	)
	for old in old_rows:
		doc = frappe.get_doc(MAPPING, old.name)
		if doc.override_roles:
			continue
		for role in roles_from_text(old.override_roles):
			if frappe.db.exists("Role", role):
				doc.append("override_roles", {"role": role})
		doc.save()
