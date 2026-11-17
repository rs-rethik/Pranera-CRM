"""Small helpers shared across the wizard's backend modules."""

import frappe
from frappe import _
from frappe.utils import cint


def field_meta(doctype: str, fieldnames) -> list[dict]:
	"""Live field metadata (label, fieldtype, options, reqd) for ``fieldnames`` on
	``doctype`` — what the frontend needs to render a plain (non-question) field,
	e.g. the Organization/Contact steps' own fields or the Address inputs."""
	meta = frappe.get_meta(doctype)
	out = []
	for fieldname in fieldnames:
		df = meta.get_field(fieldname)
		if not df:
			continue
		out.append(
			{
				"fieldname": df.fieldname,
				"label": _(df.label or df.fieldname),
				"fieldtype": df.fieldtype,
				"options": df.options,
				"reqd": cint(df.reqd),
			}
		)
	return out
