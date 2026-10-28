import json
import re

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.geo.country_info import get_all as get_country_info
from frappe.utils import add_days, cint, get_datetime, get_url, now_datetime

SETTINGS = "FCRM Settings"
LEAD, DEAL = "CRM Lead", "CRM Deal"
TEMPLATE = "WhatsApp Templates"
SENT_FIELD = "owner_follow_up_sent_on"
CLOSED_TYPES = ("Won", "Lost", "On Hold")
TEMPLATE_VALUES = 5
DEFAULT_DAYS = 7
DEFAULT_DAILY_LIMIT = 10

RECORDS = {
	LEAD: {
		"status": "CRM Lead Status",
		"owner": "lead_owner",
		"title": ("lead_name", "organization"),
		"route": "leads",
		"filters": {"converted": 0},
	},
	DEAL: {
		"status": "CRM Deal Status",
		"owner": "deal_owner",
		"title": ("organization", "lead_name"),
		"route": "deals",
		"filters": {},
	},
}

ACTIVITY = [
	("Comment", "reference_doctype", "reference_name", "creation", {"comment_type": "Comment"}),
	("Communication", "reference_doctype", "reference_name", "creation", {}),
	("FCRM Note", "reference_doctype", "reference_docname", "modified", {}),
	("CRM Call Log", "reference_doctype", "reference_docname", "modified", {}),
	("CRM Task", "reference_doctype", "reference_docname", "modified", {}),
	("WhatsApp Message", "reference_doctype", "reference_name", "creation", {}),
	("Periskope Message", None, {LEAD: "crm_lead", DEAL: "crm_deal"}, "creation", {}),
]

SENT = {
	"fieldname": SENT_FIELD,
	"label": "Owner Follow-up Sent On",
	"fieldtype": "Datetime",
	"read_only": 1,
	"hidden": 1,
	"no_copy": 1,
	"insert_after": "status",
}


def settings_fields() -> list[dict]:
	fields = [
		{
			"fieldname": "owner_follow_up_section",
			"label": "Owner Follow-up on WhatsApp",
			"fieldtype": "Section Break",
			"insert_after": "enable_convert_to_deal_wizard",
		},
		{
			"fieldname": "enable_owner_follow_up",
			"label": "Enable Owner Follow-up",
			"fieldtype": "Check",
			"default": "0",
			"description": "WhatsApp the owner of an open lead or deal that has had no activity for the set "
			"days, from the outgoing account in WhatsApp Settings.",
			"insert_after": "owner_follow_up_section",
		},
		{
			"fieldname": "owner_follow_up_days",
			"label": "No Activity For (Days)",
			"fieldtype": "Int",
			"default": str(DEFAULT_DAYS),
			"insert_after": "enable_owner_follow_up",
		},
		{
			"fieldname": "owner_follow_up_daily_limit",
			"label": "Most Follow-ups per Owner per Day",
			"fieldtype": "Int",
			"default": str(DEFAULT_DAILY_LIMIT),
			"description": "The rest go on the next days, the longest idle first. Empty or 0: 10.",
			"insert_after": "owner_follow_up_days",
		},
	]
	if frappe.db.exists("DocType", TEMPLATE):
		fields.append(
			{
				"fieldname": "owner_follow_up_template",
				"label": "WhatsApp Template",
				"fieldtype": "Link",
				"options": TEMPLATE,
				"description": "An approved template with 5 values, in this order: owner name, "
				"Lead or Deal, its name, days, link.",
				"insert_after": "owner_follow_up_daily_limit",
			}
		)
	return fields


def ensure_fields():
	create_custom_fields({SETTINGS: settings_fields(), LEAD: [SENT], DEAL: [SENT]}, update=True)


def config() -> frappe._dict | None:
	meta = frappe.get_meta(SETTINGS)
	if not meta.has_field("owner_follow_up_template") or not frappe.get_meta(LEAD).has_field(SENT_FIELD):
		return None
	settings = frappe.get_cached_doc(SETTINGS)
	if not cint(settings.enable_owner_follow_up) or not settings.owner_follow_up_template:
		return None
	account = frappe.db.get_single_value("WhatsApp Settings", "default_outgoing_account")
	if not account:
		frappe.log_error(
			title="Pranera CRM: owner follow-up",
			message="No default outgoing account in WhatsApp Settings.",
		)
		return None
	values = frappe.db.get_value(TEMPLATE, settings.owner_follow_up_template, "sample_values") or ""
	if len([v for v in values.split(",") if v.strip()]) != TEMPLATE_VALUES:
		frappe.log_error(
			title="Pranera CRM: owner follow-up",
			message=f"Template {settings.owner_follow_up_template} must have {TEMPLATE_VALUES} sample values.",
		)
		return None
	return frappe._dict(
		days=cint(settings.owner_follow_up_days) or DEFAULT_DAYS,
		limit=cint(settings.owner_follow_up_daily_limit) or DEFAULT_DAILY_LIMIT,
		template=settings.owner_follow_up_template,
		account=account,
	)


def run() -> list[tuple[str, str]]:
	cfg = config()
	if not cfg:
		return []
	cutoff = add_days(now_datetime(), -cfg.days)
	due = []
	for doctype in RECORDS:
		due.extend(idle_records(doctype, cutoff))
	due.sort(key=lambda r: r.idle_since)

	sent, per_owner, phones = [], {}, {}
	for record in due:
		if per_owner.get(record.owner, 0) >= cfg.limit:
			continue
		if record.owner not in phones:
			phones[record.owner] = owner_contact(record.owner)
		contact = phones[record.owner]
		if not contact:
			continue
		try:
			send(cfg, record, contact)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Pranera CRM: owner follow-up for {record.doctype} {record.name} failed")
			continue
		frappe.db.set_value(record.doctype, record.name, SENT_FIELD, now_datetime(), update_modified=False)
		frappe.db.commit()
		per_owner[record.owner] = per_owner.get(record.owner, 0) + 1
		sent.append((record.doctype, record.name))
	return sent


def idle_records(doctype: str, cutoff) -> list:
	spec = RECORDS[doctype]
	closed = frappe.get_all(spec["status"], filters={"type": ["in", CLOSED_TYPES]}, pluck="name")
	filters = {spec["owner"]: ["is", "set"], "modified": ["<", cutoff], **spec["filters"]}
	if closed:
		filters["status"] = ["not in", closed]
	rows = frappe.get_all(
		doctype,
		filters=filters,
		fields=["name", "status", "modified", SENT_FIELD, f"{spec['owner']} as owner", *spec["title"]],
	)
	if not rows:
		return []
	latest = last_activity(doctype, [r.name for r in rows])
	out = []
	for row in rows:
		idle_since = max(get_datetime(row.modified), latest.get(row.name) or get_datetime(row.modified))
		sent_on = row.get(SENT_FIELD)
		if idle_since >= cutoff or (sent_on and get_datetime(sent_on) >= cutoff):
			continue
		title = next((row.get(f) for f in spec["title"] if row.get(f)), row.name)
		out.append(
			frappe._dict(
				doctype=doctype,
				name=row.name,
				owner=row.owner,
				title=title,
				idle_since=idle_since,
				days=(now_datetime() - idle_since).days,
			)
		)
	return out


def last_activity(doctype: str, names: list[str]) -> dict:
	latest = {}
	for source, ref_doctype_field, ref_name_field, date_field, extra in ACTIVITY:
		if not frappe.db.exists("DocType", source):
			continue
		if ref_doctype_field:
			name_field = ref_name_field
			filters = {ref_doctype_field: doctype, name_field: ["in", names], **extra}
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


def owner_contact(user: str) -> frappe._dict | None:
	row = frappe.db.get_value(
		"User", user, ["enabled", "first_name", "full_name", "mobile_no", "phone"], as_dict=True
	)
	if not row or not row.enabled:
		return None
	number = whatsapp_number(row.mobile_no or row.phone)
	if not number:
		return None
	return frappe._dict(name=row.first_name or row.full_name or user, number=number)


def whatsapp_number(raw: str | None) -> str | None:
	if not raw:
		return None
	digits = re.sub(r"\D", "", raw)
	if raw.strip().startswith("+") or len(digits) > 10:
		return digits or None
	if len(digits) != 10:
		return None
	country = frappe.db.get_single_value("System Settings", "country")
	isd = re.sub(r"\D", "", (get_country_info().get(country) or {}).get("isd") or "")
	return f"{isd}{digits}" if isd else None


def send(cfg, record, contact):
	link = get_url(f"/crm/{RECORDS[record.doctype]['route']}/{record.name}")
	kind = _("Lead") if record.doctype == LEAD else _("Deal")
	values = [contact.name, kind, f"{record.title} ({record.name})", str(record.days), link]
	frappe.get_doc(
		{
			"doctype": "WhatsApp Message",
			"type": "Outgoing",
			"message_type": "Template",
			"content_type": "text",
			"to": contact.number,
			"template": cfg.template,
			"whatsapp_account": cfg.account,
			"body_param": json.dumps({str(i): v for i, v in enumerate(values, 1)}),
		}
	).insert(ignore_permissions=True)
