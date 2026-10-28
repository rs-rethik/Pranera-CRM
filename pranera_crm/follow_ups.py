import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import add_days, cint, get_datetime, now_datetime

LEAD, DEAL = "CRM Lead", "CRM Deal"
TASK = "CRM Task"
DEFAULT_DAYS = 7
OPEN_TASK = ("Backlog", "Todo", "In Progress")

RECORDS = {
	LEAD: {"status": "CRM Lead Status", "owner": "lead_owner", "filters": {"converted": 0}},
	DEAL: {"status": "CRM Deal Status", "owner": "deal_owner", "filters": {}},
}

ACTIVITY = [
	("Comment", "reference_doctype", "reference_name", "creation", {"comment_type": "Comment"}),
	("Communication", "reference_doctype", "reference_name", "creation", {}),
	("FCRM Note", "reference_doctype", "reference_docname", "modified", {}),
	("CRM Call Log", "reference_doctype", "reference_docname", "modified", {}),
	(TASK, "reference_doctype", "reference_docname", "modified", {}),
	("WhatsApp Message", "reference_doctype", "reference_name", "creation", {}),
	("Periskope Message", None, {LEAD: "crm_lead", DEAL: "crm_deal"}, "creation", {}),
]

STATUS_FIELDS = [
	{
		"fieldname": "waiting_on",
		"label": "Waiting On",
		"fieldtype": "Select",
		"options": "\nUs\nBuyer",
		"in_list_view": 1,
		"insert_after": "type",
	},
	{
		"fieldname": "follow_up_after_days",
		"label": "Follow-up After (Days)",
		"fieldtype": "Int",
		"default": str(DEFAULT_DAYS),
		"depends_on": "eval:doc.waiting_on == 'Buyer'",
		"description": "No activity for this many days creates a follow-up task for the owner.",
		"insert_after": "waiting_on",
	},
]

CUSTOM_FIELDS = {
	"CRM Lead Status": STATUS_FIELDS,
	"CRM Deal Status": STATUS_FIELDS,
	TASK: [
		{
			"fieldname": "auto_follow_up",
			"label": "Auto Follow-up",
			"fieldtype": "Check",
			"read_only": 1,
			"insert_after": "reference_docname",
		}
	],
}


def ensure_fields():
	create_custom_fields(CUSTOM_FIELDS, update=True)


def _ready() -> bool:
	return frappe.get_meta(TASK).has_field("auto_follow_up") and frappe.get_meta("CRM Lead Status").has_field(
		"waiting_on"
	)


def buyer_statuses(status_doctype: str) -> dict[str, int]:
	rows = frappe.get_all(
		status_doctype, filters={"waiting_on": "Buyer"}, fields=["name", "follow_up_after_days"]
	)
	return {row.name: cint(row.follow_up_after_days) or DEFAULT_DAYS for row in rows}


def create() -> list[str]:
	if not _ready():
		return []
	created = []
	for doctype, spec in RECORDS.items():
		statuses = buyer_statuses(spec["status"])
		if not statuses:
			continue
		records = frappe.get_all(
			doctype,
			filters={"status": ["in", list(statuses)], **spec["filters"]},
			fields=["name", "status", "modified", spec["owner"] + " as owner"],
		)
		if not records:
			continue
		names = [r.name for r in records]
		last = last_activity(doctype, names)
		with_open_task = set(
			frappe.get_all(
				TASK,
				filters={
					"reference_doctype": doctype,
					"reference_docname": ["in", names],
					"auto_follow_up": 1,
					"status": ["in", OPEN_TASK],
				},
				pluck="reference_docname",
			)
		)
		for record in records:
			days = statuses[record.status]
			since = max(get_datetime(record.modified), last.get(record.name) or get_datetime(record.modified))
			if since > add_days(now_datetime(), -days) or record.name in with_open_task:
				continue
			if not record.owner or not frappe.db.get_value("User", record.owner, "enabled"):
				continue
			try:
				created.append(_task(doctype, record, days))
			except Exception:
				frappe.log_error(title=f"Pranera CRM: follow-up task for {doctype} {record.name} failed")
	if created:
		frappe.db.commit()
	return created


def last_activity(doctype: str, names: list[str]) -> dict:
	latest = {}
	for source, ref_doctype_field, ref_name_field, date_field, extra in ACTIVITY:
		if not frappe.db.exists("DocType", source):
			continue
		if ref_doctype_field:
			filters = {ref_doctype_field: doctype, ref_name_field: ["in", names], **extra}
			name_field = ref_name_field
		else:
			name_field = ref_name_field.get(doctype)
			if not name_field or not frappe.get_meta(source).has_field(name_field):
				continue
			filters = {name_field: ["in", names], **extra}
		for row in frappe.get_all(
			source,
			filters=filters,
			fields=[f"{name_field} as record", f"max({date_field}) as at"],
			group_by=name_field,
		):
			at = get_datetime(row.at)
			if row.record and (row.record not in latest or at > latest[row.record]):
				latest[row.record] = at
	return latest


def _task(doctype: str, record, days: int) -> str:
	task = frappe.get_doc(
		{
			"doctype": TASK,
			"title": _("Follow up: no activity for {0} days").format(days),
			"description": _("{0} {1} has been in '{2}' with no activity for {3} days.").format(
				_(doctype), record.name, record.status, days
			),
			"status": "Todo",
			"priority": "Medium",
			"assigned_to": record.owner,
			"due_date": now_datetime(),
			"reference_doctype": doctype,
			"reference_docname": record.name,
			"auto_follow_up": 1,
		}
	)
	task.insert(ignore_permissions=True)
	return task.name
