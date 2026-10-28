"""Lead closure reasons on leads, Deal lost reasons on deals.

CRM Lead and CRM Deal share one CRM Lost Reason master. Each reason gets an "Applies To" (Lead,
Deal or Both) and, for lead reasons, the lead status it belongs to (Spam is for Junk, Below MOQ for
Not Suitable and so on):

1. The Lost Reason picker in the CRM lists only the reasons for the record it is on. The picker
   says nothing about that record, so the page it was opened from tells (/crm/leads/... or
   /crm/deals/...); anywhere else every reason is listed.
2. Saving a closed lead or deal with a reason of the other kind, or a lead reason of another lead
   status, is refused. This holds however the record is saved (form, import, API).
3. A lead moving to a status with exactly one reason gets it filled in (No Response:
   "No reply after 3 attempts"), as the CRM only asks for a reason on Lost statuses.

A reason with no Applies To counts as Both, so nothing is hidden before it is tagged.
"""

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

# The agreed reasons: (reason, applies to, lead status, description).
SEED = [
	("Price Not Okay", "Deal", None, "Commercial: our price above buyer's target even after revision"),
	("Payment Terms Not Agreed", "Deal", None, "Commercial: buyer wants credit / terms we cannot give"),
	("MOQ Not Met", "Deal", None, "Commercial: final quantity below our minimum"),
	("Sample Charge Not Accepted", "Deal", None, "Commercial: buyer unwilling to pay for sample / lab dip"),
	(
		"Quality Not Approved",
		"Deal",
		None,
		"Product / Quality: sample / lab dip rejected on hand-feel, GSM, shade or fastness",
	),
	(
		"Spec Not Achievable",
		"Deal",
		None,
		"Product / Quality: buyer's spec (fastness, finish, width etc.) beyond our capability",
	),
	(
		"Not in Our Range",
		"Both",
		"Not Suitable",
		"Product / Quality: woven, cotton, export-grade or other fabric we do not make",
	),
	("Lead Time Not Met", "Deal", None, "Delivery: buyer needed it faster than we could commit"),
	("Stock Not Available", "Deal", None, "Delivery: ready stock required; not available"),
	(
		"Bought from Competitor",
		"Deal",
		None,
		"Buyer-side: order placed elsewhere (record competitor name in remarks)",
	),
	(
		"Customer Did Not Get Order",
		"Deal",
		None,
		"Buyer-side: buyer's own order from their customer fell through",
	),
	("Customer No Response", "Deal", None, "Buyer-side: buyer stopped responding after quote"),
	(
		"Credit Risk \u2013 Declined by Us",
		"Deal",
		None,
		"Buyer-side: we chose not to proceed due to payment history / risk",
	),
	("Other", "Both", None, "Only if none apply - remarks mandatory"),
	("Below MOQ", "Lead", "Not Suitable", "Lead closure: Not Suitable"),
	("Price Mismatch", "Lead", "Not Suitable", "Lead closure: Not Suitable"),
	("Bought Elsewhere", "Lead", "Not Suitable", "Lead closure: Not Suitable"),
	("Credit Risk", "Lead", "Not Suitable", "Lead closure: Not Suitable"),
	("No reply after 3 attempts", "Lead", "No Response", "Lead closure: No Response"),
	("Spam", "Lead", "Junk", "Lead closure: Junk"),
	("Duplicate", "Lead", "Junk", "Lead closure: Junk"),
	("Wrong Number", "Lead", "Junk", "Lead closure: Junk"),
	("Existing Customer", "Lead", "Junk", "Lead closure: Junk (raise a Deal directly instead)"),
]


def _ready() -> bool:
	"""The fields exist (they are added on install and migrate; until then nothing changes)."""
	return frappe.get_meta(REASON).has_field("applies_to")


def ensure_fields():
	create_custom_fields(CUSTOM_FIELDS, update=True)


def seed():
	"""Create the agreed reasons that are missing and tag each one (a patch: runs once, so later
	edits to a reason stay)."""
	ensure_fields()
	for reason, applies_to, lead_status, description in SEED:
		if lead_status and not frappe.db.exists("CRM Lead Status", lead_status):
			lead_status = None
		values = {"applies_to": applies_to, "lead_status": lead_status}
		if frappe.db.exists(REASON, reason):
			frappe.db.set_value(REASON, reason, values, update_modified=False)
		else:
			frappe.get_doc(
				{"doctype": REASON, "lost_reason": reason, "description": description, **values}
			).insert(ignore_permissions=True)


# --- The picker ----------------------------------------------------------------------------------


def _record_doctype(reference_doctype: str | None = None) -> str | None:
	"""CRM Lead or CRM Deal when the picker is on one, else None."""
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
	"""The Lost Reason picker (standard_queries): only the reasons for the record it is on."""
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


# --- On save --------------------------------------------------------------------------------------


def _status_type(doc) -> str | None:
	status_doctype = "CRM Lead Status" if doc.doctype == LEAD else "CRM Deal Status"
	return frappe.get_cached_value(status_doctype, doc.status, "type") if doc.status else None


def validate(doc, method=None):
	"""doc_events validate of CRM Lead and CRM Deal."""
	if not _ready():
		return
	if doc.doctype == LEAD and doc.has_value_changed("status") and not doc.lost_reason:
		doc.lost_reason = only_reason(doc.status)
	if not doc.lost_reason or _status_type(doc) not in CLOSED_TYPES:
		return
	if not (doc.has_value_changed("lost_reason") or doc.has_value_changed("status")):
		return  # a record closed before these rules keeps its reason
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
	"""The reason of a lead status that has exactly one."""
	if not lead_status:
		return None
	reasons = frappe.get_all(
		REASON,
		filters={"lead_status": lead_status, "applies_to": ["!=", "Deal"]},
		pluck="name",
		limit=2,
	)
	return reasons[0] if len(reasons) == 1 else None
