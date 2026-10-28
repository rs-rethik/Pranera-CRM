from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

LEAD, DEAL = "CRM Lead", "CRM Deal"
REASON = "CRM Lost Reason"
APPLIES_TO = {LEAD: "Lead", DEAL: "Deal"}
CLOSED_TYPES = ("Lost", "On Hold")

CUSTOM_FIELDS = {
	REASON: [
		{
			"fieldname": "applies_to",
			"label": "Applies To",
			"fieldtype": "Select",
			"options": "Both\nLead\nDeal",
			"default": "Both",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"insert_after": "lost_reason",
		},
		{
			"fieldname": "lead_status",
			"label": "Lead Status",
			"fieldtype": "Link",
			"options": "CRM Lead Status",
			"in_list_view": 1,
			"depends_on": "eval:doc.applies_to != 'Deal'",
			"description": "Only for leads in this status. Empty: any closed lead.",
			"insert_after": "applies_to",
		},
	]
}


def _ready() -> bool:
	return frappe.get_meta(REASON).has_field("applies_to")


def ensure_fields():
	create_custom_fields(CUSTOM_FIELDS, update=True)


def _record_doctype(reference_doctype: str | None = None) -> str | None:
	if reference_doctype in APPLIES_TO:
		return reference_doctype
	request = getattr(frappe.local, "request", None)
	path = urlparse(request.headers.get("Referer", "") if request else "").path
	if "/crm/leads" in path:
		return LEAD
	if "/crm/deals" in path:
		return DEAL
	return None


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search(doctype, txt, searchfield, start, page_len, filters, **kwargs):
	conditions = []
	record = _record_doctype(kwargs.get("reference_doctype"))
	if record and _ready():
		other = DEAL if record == LEAD else LEAD
		conditions.append([REASON, "applies_to", "!=", APPLIES_TO[other]])
	return frappe.get_list(
		REASON,
		filters=conditions + (filters if isinstance(filters, list) else []),
		or_filters=[[REASON, "name", "like", f"%{txt}%"], [REASON, "description", "like", f"%{txt}%"]],
		fields=["name", "description"],
		order_by="name asc",
		limit_start=start,
		limit_page_length=page_len,
		as_list=True,
	)


def _status_type(doc) -> str | None:
	status_doctype = "CRM Lead Status" if doc.doctype == LEAD else "CRM Deal Status"
	return frappe.get_cached_value(status_doctype, doc.status, "type") if doc.status else None


def validate(doc, method=None):
	if not _ready():
		return
	if doc.doctype == LEAD and doc.has_value_changed("status") and not doc.lost_reason:
		doc.lost_reason = only_reason(doc.status)
	if not doc.lost_reason or _status_type(doc) not in CLOSED_TYPES:
		return
	if not (doc.has_value_changed("lost_reason") or doc.has_value_changed("status")):
		return
	reason = frappe.db.get_value(REASON, doc.lost_reason, ["applies_to", "lead_status"], as_dict=True)
	if not reason:
		return
	kind = APPLIES_TO[doc.doctype]
	if (reason.applies_to or "Both") not in ("Both", kind):
		frappe.throw(
			_("'{0}' is a {1} reason. Please pick a {2} reason.").format(
				doc.lost_reason, _(reason.applies_to), _(kind)
			),
			title=_("Wrong Lost Reason"),
		)
	if doc.doctype == LEAD and reason.lead_status and reason.lead_status != doc.status:
		frappe.throw(
			_("'{0}' is a reason for '{1}' leads. Please pick a reason for '{2}'.").format(
				doc.lost_reason, reason.lead_status, doc.status
			),
			title=_("Wrong Lost Reason"),
		)


def only_reason(lead_status: str | None) -> str | None:
	if not lead_status:
		return None
	reasons = frappe.get_all(
		REASON,
		filters={"lead_status": lead_status, "applies_to": ["!=", "Deal"]},
		pluck="name",
		limit=2,
	)
	return reasons[0] if len(reasons) == 1 else None
