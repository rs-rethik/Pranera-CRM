"""The CRM conversion report: a PDF of lead conversions sent on WhatsApp, from the company's WhatsApp
account, to the users set in Conversion Report Settings, on a schedule or with Send Now.

For a period it counts, in total, per sales person and per territory (grouped by region):
- New leads: CRM Leads created in the period.
- Converted: those new leads that have become a deal (a CRM Deal made from the lead, or the lead's
  Converted tick), and the conversion rate (converted / new leads).
- Deals won: CRM Deals whose status is a Won-type status and whose closed date (set by the CRM when a
  deal is first won) is in the period, and their value.
- Leads not converted: the period's new leads that are not a deal yet, with their current status,
  counted per status and per sales person, and listed (the first PENDING_LIMIT of them).

The sales person is the record's Sales Person (custom_sales_person, or sales_person), else its owner.

Meta takes a free WhatsApp message only within 24 hours of the person's last message, so the report
goes as an approved template whose Document header carries the PDF (uploaded to Meta first, so no
public link is made). Each send is saved as an Outgoing WhatsApp Message, like the owner follow-up."""

import json
from collections import Counter, defaultdict

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	add_months,
	cint,
	date_diff,
	escape_html,
	flt,
	fmt_money,
	format_date,
	format_datetime,
	get_datetime,
	get_first_day,
	get_last_day,
	get_time,
	getdate,
	now_datetime,
	today,
)

SETTINGS = "Conversion Report Settings"
TEMPLATE = "WhatsApp Templates"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
NO_PERSON = "Not assigned"
NO_TERRITORY = "No territory"
NO_STATUS = "No status"
# a lead list longer than this is cut, so a monthly report stays a few pages; the rest are in the CRM
PENDING_LIMIT = 100
# CRM Lead Status types, in the order a lead moves through them; a Won-type status on a lead that has
# no deal yet is shown as its own column
STAGES = ("Open", "Ongoing", "On Hold", "Lost", "Won")
STAGE_LABELS = {"Won": "Won, no deal yet"}
PRESETS = {
	"yesterday": "Yesterday",
	"last_7_days": "Last 7 days",
	"last_week": "Last week (Monday to Sunday)",
	"this_month": "This month so far",
	"last_month": "Last month",
}


# --- Periods ---------------------------------------------------------------------------------------


def period(preset: str, ref=None) -> tuple:
	"""(from_date, to_date) for a preset, counted back from `ref` (today)."""
	day = getdate(ref or today())
	if preset == "yesterday":
		d = add_days(day, -1)
		return getdate(d), getdate(d)
	if preset == "last_7_days":
		return getdate(add_days(day, -7)), getdate(add_days(day, -1))
	if preset == "last_week":
		start = add_days(day, -day.weekday() - 7)
		return getdate(start), getdate(add_days(start, 6))
	if preset == "this_month":
		return getdate(get_first_day(day)), day
	if preset == "last_month":
		prev = add_months(day, -1)
		return getdate(get_first_day(prev)), getdate(get_last_day(prev))
	frappe.throw(_("Unknown period {0}").format(preset))


def scheduled_period(frequency: str, ref=None) -> tuple:
	return period({"Daily": "yesterday", "Weekly": "last_week", "Monthly": "last_month"}[frequency], ref)


def period_label(from_date, to_date) -> str:
	f, t = getdate(from_date), getdate(to_date)
	if f == t:
		return format_date(f, "d MMM yyyy")
	if f.year == t.year:
		return f"{format_date(f, 'd MMM')} to {format_date(t, 'd MMM yyyy')}"
	return f"{format_date(f, 'd MMM yyyy')} to {format_date(t, 'd MMM yyyy')}"


# --- Data ------------------------------------------------------------------------------------------


def _person_field(doctype: str) -> str | None:
	meta = frappe.get_meta(doctype)
	return next((f for f in ("custom_sales_person", "sales_person") if meta.has_field(f)), None)


def _owner_names(users) -> dict:
	users = [u for u in set(users) if u]
	if not users:
		return {}
	return {
		r.name: r.full_name or r.name
		for r in frappe.get_all("User", filters={"name": ("in", users)}, fields=["name", "full_name"])
	}


def _rate(part, whole) -> float:
	return round(100.0 * part / whole, 1) if whole else 0.0


def regions() -> dict:
	"""Each territory's region: its top-level group under the root of the tree (KONGU, ROTN, ROI, ...),
	so a district under a state still counts under the state's region. A region counts as its own
	region; the root has none."""
	parent = dict(frappe.get_all("CRM Territory", fields=["name", "parent_crm_territory"], as_list=True))
	out = {}
	for name in parent:
		chain, node = [], name
		while node and node not in chain and len(chain) < 50:
			chain.append(node)
			node = parent.get(node)
		# chain ends at the root; the region is the node just below it
		out[name] = chain[-2] if len(chain) >= 2 else ""
	return out


def build(from_date, to_date) -> dict:
	"""The report's numbers for the period (dates inclusive)."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	if from_date > to_date:
		frappe.throw(_("The start date is after the end date."))
	start, end = f"{from_date} 00:00:00", f"{to_date} 23:59:59.999999"

	lead_person = _person_field("CRM Lead")
	leads = frappe.db.sql(
		f"""select l.name, l.territory, l.lead_owner as owner,
			{f"l.`{lead_person}`" if lead_person else "null"} as person,
			(ifnull(l.converted, 0) = 1
				or exists(select 1 from `tabCRM Deal` d where d.lead = l.name)) as converted
		from `tabCRM Lead` l
		where l.creation between %(start)s and %(end)s""",
		{"start": start, "end": end},
		as_dict=True,
	)
	deal_person = _person_field("CRM Deal")
	won = frappe.db.sql(
		f"""select d.name, d.territory, d.deal_owner as owner, d.currency,
			{f"d.`{deal_person}`" if deal_person else "null"} as person,
			coalesce(nullif(d.deal_value, 0), d.expected_deal_value, 0) as value
		from `tabCRM Deal` d
		join `tabCRM Deal Status` s on s.name = d.status
		where s.type = 'Won' and d.closed_date between %(from)s and %(to)s""",
		{"from": from_date, "to": to_date},
		as_dict=True,
	)
	deals_created = frappe.db.count("CRM Deal", {"creation": ("between", [start, end])})

	owners = _owner_names([r.owner for r in leads + won if not r.person])

	def person_of(r):
		return r.person or owners.get(r.owner) or NO_PERSON

	def territory_of(r):
		return r.territory or NO_TERRITORY

	def table(key):
		groups = defaultdict(lambda: {"leads": 0, "converted": 0, "won": 0, "value": 0.0})
		for r in leads:
			g = groups[key(r)]
			g["leads"] += 1
			g["converted"] += 1 if r.converted else 0
		for r in won:
			g = groups[key(r)]
			g["won"] += 1
			g["value"] += flt(r.value)
		rows = [{"name": k, **v, "rate": _rate(v["converted"], v["leads"])} for k, v in groups.items()]
		blank = (NO_PERSON, NO_TERRITORY)
		rows.sort(key=lambda r: (r["name"] in blank, -r["leads"], -r["won"], -r["value"], r["name"]))
		return rows

	territories = table(territory_of)
	region = regions()
	for r in territories:
		r["parent"] = region.get(r["name"]) or ""

	total_leads = len(leads)
	total_converted = sum(1 for r in leads if r.converted)
	pending = not_converted([r for r in leads if not r.converted], person_of, territory_of)
	currencies = Counter(r.currency for r in won if r.currency)
	return {
		"from_date": str(from_date),
		"to_date": str(to_date),
		"label": period_label(from_date, to_date),
		"currency": currencies.most_common(1)[0][0]
		if currencies
		else (frappe.db.get_default("currency") or "INR"),
		"summary": {
			"leads": total_leads,
			"converted": total_converted,
			"rate": _rate(total_converted, total_leads),
			"deals_created": deals_created,
			"won": len(won),
			"value": sum(flt(r.value) for r in won),
		},
		"people": table(person_of),
		"territories": territories,
		"pending": pending,
	}


def not_converted(rows, person_of, territory_of) -> dict:
	"""The period's leads that are not a deal yet: a count per status (in the CRM's status order),
	per sales person by status type, and the leads themselves (oldest first within each status)."""
	statuses = {
		s.name: s
		for s in frappe.get_all("CRM Lead Status", fields=["name", "type", "position"], order_by="position")
	}
	details = {
		d.name: d
		for d in frappe.get_all(
			"CRM Lead",
			filters={"name": ("in", [r.name for r in rows] or [""])},
			fields=["name", "lead_name", "first_name", "organization", "status", "creation"],
		)
	}
	order = {name: i for i, name in enumerate(statuses)}
	today_ = getdate(today())

	leads, by_status, people = [], Counter(), defaultdict(Counter)
	for r in rows:
		d = details.get(r.name) or frappe._dict()
		status = d.status or NO_STATUS
		stage = (statuses.get(status) or frappe._dict()).type or "Open"
		person = person_of(r)
		by_status[status] += 1
		people[person][stage] += 1
		leads.append(
			{
				"name": r.name,
				"lead": d.lead_name or d.first_name or r.name,
				"organization": d.organization or "",
				"person": person,
				"territory": territory_of(r),
				"status": status,
				"stage": stage,
				"created": str(getdate(d.creation)) if d.creation else "",
				"days": date_diff(today_, getdate(d.creation)) if d.creation else 0,
			}
		)
	leads.sort(key=lambda r: (order.get(r["status"], len(order)), r["created"], r["name"]))

	total = len(rows)
	status_rows = [
		{
			"name": name,
			"stage": (statuses.get(name) or frappe._dict()).type or "Open",
			"leads": n,
			"share": _rate(n, total),
		}
		for name, n in sorted(by_status.items(), key=lambda kv: (order.get(kv[0], len(order)), kv[0]))
	]
	stages = [s for s in STAGES if any(c[s] for c in people.values())]
	people_rows = [
		{"name": k, **{s: c[s] for s in stages}, "total": sum(c.values())} for k, c in people.items()
	]
	people_rows.sort(key=lambda r: (r["name"] == NO_PERSON, -r["total"], r["name"]))
	return {
		"total": total,
		"stages": stages,
		"by_status": status_rows,
		"people": people_rows,
		"leads": leads[:PENDING_LIMIT],
		"more": max(total - PENDING_LIMIT, 0),
	}


# --- PDF -------------------------------------------------------------------------------------------


def company_name() -> str:
	return (
		frappe.db.get_default("company")
		or frappe.db.get_single_value("Periskope Settings", "brand_name")
		or frappe.db.get_single_value("System Settings", "app_name")
		or "CRM"
	)


def render_html(data: dict) -> str:
	cur = data["currency"]
	s = data["summary"]

	def money(v):
		return escape_html(fmt_money(v, precision=0, currency=cur))

	def bar(rate):
		width = max(0.0, min(rate, 100.0))
		return (
			f'<div class="rate"><span class="bar"><i style="width:{width}%"></i></span><b>{rate:g}%</b></div>'
		)

	def line(r, cls=""):
		cls = cls or ("muted" if r["name"] in (NO_PERSON, NO_TERRITORY) else "")
		return (
			f"<tr class='{cls}'><td>{escape_html(r['name'])}</td>"
			f"<td class='n'>{r['leads']}</td><td class='n'>{r['converted']}</td>"
			f"<td>{bar(r['rate'])}</td><td class='n'>{r['won']}</td>"
			f"<td class='n'>{money(r['value'])}</td></tr>"
		)

	empty = "<tr><td colspan='6' class='empty'>No leads or won deals in this period.</td></tr>"

	def people_rows():
		return "".join(line(r) for r in data["people"]) or empty

	def territory_rows():
		"""Territories under their region (the parent territory), each region with its subtotal."""
		if not data["territories"]:
			return empty
		regions = defaultdict(list)
		for r in data["territories"]:
			regions[r["parent"] or ""].append(r)
		if set(regions) == {""}:
			return "".join(line(r) for r in data["territories"])

		def subtotal(name, items):
			t = {k: sum(r[k] for r in items) for k in ("leads", "converted", "won", "value")}
			return {"name": name, **t, "rate": _rate(t["converted"], t["leads"])}

		groups = [subtotal(k, v) | {"items": v} for k, v in regions.items() if k]
		groups.sort(key=lambda g: (-g["leads"], -g["won"], g["name"]))
		out = []
		for g in groups:
			out.append(line(g, "region"))
			if [r["name"] for r in g["items"]] == [g["name"]]:
				continue  # all of the region's records are on the region itself
			for r in g["items"]:
				label = f"{r['name']} (no sub-territory)" if r["name"] == g["name"] else r["name"]
				out.append(line(r | {"name": label}, "child"))
		# territories outside the regions, and records without a territory, at the end
		out.extend(line(r) for r in regions.get("", []))
		return "".join(out)

	def totals():
		return line({"name": "Total", **s}, "total")

	head = (
		"<th class='n'>New leads</th><th class='n'>Converted</th><th class='rate-h'>Conversion</th>"
		"<th class='n'>Deals won</th><th class='n'>Won value</th>"
	)
	best = max(data["people"], key=lambda r: (r["converted"], r["value"]), default=None)
	best_line = (
		f"Top converter: <b>{escape_html(best['name'])}</b> with {best['converted']} of {best['leads']} "
		f"new leads converted ({best['rate']:g}%)."
		if best and best["converted"] and best["name"] != NO_PERSON
		else ""
	)
	company = escape_html(company_name())
	generated = escape_html(format_datetime(now_datetime(), "d MMM yyyy, h:mm a"))
	return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
@page {{
	size: A4; margin: 16mm 14mm 18mm;
	@bottom-left {{ content: "{company} · CRM conversion report · {escape_html(data["label"])}"; font: 8pt sans-serif; color: #8a8f98; }}
	@bottom-right {{ content: "Page " counter(page) " of " counter(pages); font: 8pt sans-serif; color: #8a8f98; }}
}}
* {{ box-sizing: border-box; }}
body {{ font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif; color: #1f2329; font-size: 9.5pt; margin: 0; }}
.top {{ display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #0f5e4f; padding-bottom: 8pt; }}
.brand {{ font-size: 9pt; letter-spacing: .12em; text-transform: uppercase; color: #0f5e4f; font-weight: 700; }}
h1 {{ font-size: 19pt; margin: 2pt 0 0; }}
.period {{ text-align: right; font-size: 9pt; color: #5b616e; }}
.period b {{ display: block; font-size: 12pt; color: #1f2329; }}
.tiles {{ display: flex; gap: 7pt; margin: 14pt 0 6pt; }}
.tile {{ flex: 1; border: 1px solid #e3e6ea; border-radius: 7pt; padding: 8pt 9pt; }}
.tile.wide {{ flex: 1.6; }}
.tile .v.money {{ font-size: 13pt; white-space: nowrap; padding-top: 2pt; }}
.tile.key {{ background: #0f5e4f; border-color: #0f5e4f; color: #fff; }}
.tile .v {{ font-size: 16pt; font-weight: 700; line-height: 1.1; }}
.tile .l {{ font-size: 7.5pt; text-transform: uppercase; letter-spacing: .06em; color: #6b7280; margin-top: 3pt; }}
.tile.key .l {{ color: #cfe7e1; }}
.note {{ font-size: 8.5pt; color: #5b616e; margin: 4pt 0 0; }}
h2 {{ font-size: 12pt; margin: 18pt 0 6pt; }}
table {{ width: 100%; border-collapse: collapse; }}
thead {{ display: table-header-group; }}
tr {{ page-break-inside: avoid; }}
th {{ text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; font-weight: 600; padding: 5pt 6pt; border-bottom: 1px solid #d5d9de; }}
td {{ padding: 4pt 6pt; border-bottom: 1px solid #eef0f2; }}
.region td {{ font-weight: 700; background: #eef6f4; border-bottom: 1px solid #d5e6e1; padding-top: 5pt; padding-bottom: 5pt; }}
.child td:first-child {{ padding-left: 16pt; }}
.region {{ page-break-after: avoid; }}
.n {{ text-align: right; white-space: nowrap; }}
.muted td {{ color: #8a8f98; font-style: italic; }}
.total td {{ font-weight: 700; border-top: 1.5px solid #1f2329; border-bottom: none; background: #f6f8f8; }}
.rate-h {{ width: 26%; }}
.rate {{ display: flex; align-items: center; gap: 6pt; }}
.bar {{ flex: 1; height: 6pt; background: #e8eef0; border-radius: 3pt; overflow: hidden; }}
.bar i {{ display: block; height: 100%; background: #14a37f; border-radius: 3pt; }}
.rate b {{ width: 34pt; text-align: right; font-weight: 600; }}
.empty {{ text-align: center; color: #8a8f98; padding: 14pt; }}
.list td {{ font-size: 8.5pt; }}
.list .org {{ color: #5b616e; }}
.pill {{ display: inline-block; padding: 1pt 5pt; border-radius: 6pt; font-size: 7.5pt; background: #eef0f2; white-space: nowrap; }}
.pill.Open {{ background: #e6f0fb; color: #1d5fa8; }}
.pill.Ongoing {{ background: #fdf3dc; color: #8a5a00; }}
.pill.On.Hold {{ background: #eceef1; color: #4b5260; }}
.pill.Lost {{ background: #fbe7e7; color: #a33a3a; }}
.pill.Won {{ background: #e3f4ee; color: #0f5e4f; }}
</style></head><body>
<div class="top">
	<div><div class="brand">{company}</div><h1>CRM Conversion Report</h1></div>
	<div class="period">Period<b>{escape_html(data["label"])}</b>Generated {generated}</div>
</div>

<div class="tiles">
	<div class="tile"><div class="v">{s["leads"]}</div><div class="l">New leads</div></div>
	<div class="tile"><div class="v">{s["converted"]}</div><div class="l">Converted to deals</div></div>
	<div class="tile key"><div class="v">{s["rate"]:g}%</div><div class="l">Conversion rate</div></div>
	<div class="tile"><div class="v">{s["deals_created"]}</div><div class="l">Deals created</div></div>
	<div class="tile"><div class="v">{s["won"]}</div><div class="l">Deals won</div></div>
	<div class="tile wide"><div class="v money">{money(s["value"])}</div><div class="l">Won value</div></div>
</div>
<p class="note">{best_line}</p>

<h2>Sales person wise</h2>
<table><thead><tr><th>Sales person</th>{head}</tr></thead>
<tbody>{people_rows()}{totals()}</tbody></table>

<h2>Territory wise</h2>
<table><thead><tr><th>Territory</th>{head}</tr></thead>
<tbody>{territory_rows()}{totals()}</tbody></table>

{pending_section(data)}
</body></html>"""


def pending_section(data: dict) -> str:
	"""The "Leads not converted" part of the report (empty when every new lead is converted)."""
	p = data.get("pending") or {}
	if not p.get("total"):
		return ""

	def pill(stage, text):
		return f"<span class='pill {escape_html(stage)}'>{escape_html(text)}</span>"

	def bar(rate):
		width = max(0.0, min(rate, 100.0))
		return (
			f'<div class="rate"><span class="bar"><i style="width:{width}%"></i></span><b>{rate:g}%</b></div>'
		)

	status_rows = "".join(
		f"<tr><td>{pill(r['stage'], r['name'])}</td><td>{escape_html(r['stage'])}</td>"
		f"<td class='n'>{r['leads']}</td><td>{bar(r['share'])}</td></tr>"
		for r in p["by_status"]
	)
	stages = p["stages"]
	stage_head = "".join(f"<th class='n'>{escape_html(STAGE_LABELS.get(s, s))}</th>" for s in stages)
	people_rows = "".join(
		f"<tr class='{'muted' if r['name'] == NO_PERSON else ''}'><td>{escape_html(r['name'])}</td>"
		+ "".join(f"<td class='n'>{r[s] or ''}</td>" for s in stages)
		+ f"<td class='n'><b>{r['total']}</b></td></tr>"
		for r in p["people"]
	)
	stage_totals = "".join(f"<td class='n'>{sum(r[s] for r in p['people'])}</td>" for s in stages)
	lead_rows = "".join(
		f"<tr><td>{escape_html(r['lead'])}<div class='org'>{escape_html(r['organization'])}</div></td>"
		f"<td>{escape_html(r['person'])}</td><td>{escape_html(r['territory'])}</td>"
		f"<td>{pill(r['stage'], r['status'])}</td>"
		f"<td class='n'>{escape_html(format_date(r['created'], 'd MMM')) if r['created'] else ''}</td>"
		f"<td class='n'>{r['days']}</td></tr>"
		for r in p["leads"]
	)
	more = (
		f"<p class='note'>Showing the first {len(p['leads'])} of {p['total']} leads. "
		f"The other {p['more']} are in the CRM.</p>"
		if p["more"]
		else ""
	)
	converted = data["summary"]["converted"]
	return f"""
<h2>Leads not converted</h2>
<p class="note"><b>{p['total']}</b> of the {data['summary']['leads']} new leads in this period are not a deal yet
({converted} converted). Their status now:</p>
<table><thead><tr><th>Status</th><th>Stage</th><th class='n'>Leads</th><th class='rate-h'>Share</th></tr></thead>
<tbody>{status_rows}<tr class="total"><td>Total</td><td></td><td class='n'>{p['total']}</td><td></td></tr></tbody></table>

<h2>Not converted, by sales person</h2>
<table><thead><tr><th>Sales person</th>{stage_head}<th class='n'>Total</th></tr></thead>
<tbody>{people_rows}<tr class="total"><td>Total</td>{stage_totals}<td class='n'>{p['total']}</td></tr></tbody></table>

<h2>Lead list</h2>
<table class="list"><thead><tr><th>Lead</th><th>Sales person</th><th>Territory</th><th>Status</th>
<th class='n'>Created</th><th class='n'>Days</th></tr></thead>
<tbody>{lead_rows}</tbody></table>
{more}"""


def render_pdf(data: dict) -> bytes:
	from weasyprint import HTML

	return HTML(string=render_html(data)).write_pdf()


def file_name(data: dict) -> str:
	return f"CRM Conversion Report {data['from_date']} to {data['to_date']}.pdf"


# --- Sending ---------------------------------------------------------------------------------------


def body_values(data: dict) -> list[str]:
	"""The template's body values, in order; a template uses as many as it has variables."""
	s = data["summary"]
	return [
		data["label"],
		str(s["leads"]),
		str(s["converted"]),
		f"{s['rate']:g}%",
		str(s["won"]),
		fmt_money(s["value"], precision=0, currency=data["currency"]),
	]


def recipients(cfg) -> list[frappe._dict]:
	"""The enabled recipients with a WhatsApp number: the row's number, else the user's mobile."""
	from pranera_crm.owner_follow_up import whatsapp_number

	out = []
	for r in cfg.recipients or []:
		if not r.enabled:
			continue
		raw = r.whatsapp_number
		if not raw and r.user:
			raw = frappe.db.get_value("User", r.user, "mobile_no") or frappe.db.get_value(
				"User", r.user, "phone"
			)
		number = whatsapp_number(raw)
		name = r.recipient_name or (r.user and frappe.utils.get_fullname(r.user)) or raw or ""
		out.append(frappe._dict(name=name, user=r.user, raw=raw or "", number=number))
	return out


def account_name(cfg) -> str:
	account = cfg.whatsapp_account or frappe.db.get_single_value(
		"WhatsApp Settings", "default_outgoing_account"
	)
	if not account:
		frappe.throw(
			_("Choose a WhatsApp account, or set the default outgoing account in WhatsApp Settings.")
		)
	return account


def upload_to_meta(account_name: str, content: bytes, name: str) -> str:
	"""Upload the PDF to Meta and return its media id (kept by Meta for 30 days)."""
	import requests

	account = frappe.get_doc("WhatsApp Account", account_name)
	response = requests.post(
		f"{account.url}/{account.version}/{account.phone_id}/media",
		headers={"authorization": f"Bearer {account.get_password('token')}"},
		data={"messaging_product": "whatsapp", "type": "application/pdf"},
		files={"file": (name, content, "application/pdf")},
		timeout=60,
	)
	body = response.json() if response.content else {}
	if not response.ok or not body.get("id"):
		frappe.throw((body.get("error") or {}).get("message") or _("WhatsApp did not accept the PDF."))
	return body["id"]


def send_to(account: str, template, media_id: str, file_name: str, values: list, number: str) -> str:
	from pranera_crm.owner_follow_up import post_to_meta

	count = len([v for v in (template.sample_values or "").split(",") if v.strip()])
	components = [
		{
			"type": "header",
			"parameters": [{"type": "document", "document": {"id": media_id, "filename": file_name}}],
		}
	]
	if count:
		components.append(
			{"type": "body", "parameters": [{"type": "text", "text": v} for v in values[:count]]}
		)
	return post_to_meta(
		account,
		{
			"messaging_product": "whatsapp",
			"to": number,
			"type": "template",
			"template": {
				"name": template.actual_name or template.template_name,
				"language": {"code": template.language_code},
				"components": components,
			},
		},
	)


def log_message(account: str, template, number: str, values: list, message_id: str, file_url: str):
	"""Keep the send in WhatsApp Message, without frappe_whatsapp sending it again."""
	text = template.template or ""
	for i, value in enumerate(values, 1):
		text = text.replace(f"{{{{{i}}}}}", value)
	now = now_datetime()
	message = frappe.get_doc(
		{
			"doctype": "WhatsApp Message",
			"type": "Outgoing",
			"message_type": "Template",
			"content_type": "document",
			"to": number,
			"template": template.name,
			"whatsapp_account": account,
			"message": text,
			"attach": file_url,
			"template_parameters": json.dumps(values),
			"message_id": message_id,
			"owner": frappe.session.user,
			"modified_by": frappe.session.user,
			"creation": now,
			"modified": now,
		}
	)
	message.set_new_name()
	message.db_insert()


def send(from_date, to_date, trigger: str = "Manual") -> dict:
	"""Make the PDF for the period and send it to every enabled recipient. Returns each one's
	result; a failure for one does not stop the others."""
	cfg = frappe.get_single(SETTINGS)
	if not cfg.template:
		frappe.throw(_("Choose the WhatsApp template in Conversion Report Settings."))
	people = recipients(cfg)
	if not people:
		frappe.throw(_("Add at least one recipient in Conversion Report Settings."))
	account = account_name(cfg)
	template = frappe.get_doc(TEMPLATE, cfg.template)

	data = build(from_date, to_date)
	content = render_pdf(data)
	name = file_name(data)
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": name,
			"is_private": 1,
			"content": content,
			"attached_to_doctype": SETTINGS,
			"attached_to_name": SETTINGS,
		}
	).insert(ignore_permissions=True)
	values = body_values(data)

	media_id, upload_error = None, None
	try:
		media_id = upload_to_meta(account, content, name)
	except Exception as e:
		upload_error = str(e)[:300] or "Upload failed"

	results = []
	for p in people:
		row = {"name": p.name, "number": p.number or p.raw}
		if not p.number:
			row.update(status="Skipped", error=_("No valid WhatsApp number"))
		elif upload_error:
			row.update(status="Failed", error=upload_error)
		else:
			try:
				message_id = send_to(account, template, media_id, name, values, p.number)
				log_message(account, template, p.number, values, message_id, file.file_url)
				row["status"] = "Sent"
			except Exception as e:
				row.update(status="Failed", error=str(e)[:300])
		results.append(row)

	summary = "; ".join(
		f"{r['name']}: {r['status']}" + (f" ({r['error']})" if r.get("error") else "") for r in results
	)
	frappe.db.set_single_value(
		SETTINGS,
		{
			"last_sent_on": now_datetime(),
			"last_period": f"{data['label']} ({trigger})",
			"last_result": summary[:1000],
		},
	)
	return {"period": data["label"], "file": file.file_url, "results": results, "summary": data["summary"]}


def ensure_defaults():
	"""A Single's defaults are not saved until someone saves it: keep the send time at 09:00 and the
	schedule filled in, so the form never shows an empty or current-time value."""
	defaults = {"frequency": "Weekly", "weekday": "Monday", "month_day": 1, "send_time": "09:00:00"}
	saved = dict(
		frappe.db.sql("select field, value from `tabSingles` where doctype = %s", SETTINGS, as_list=True)
	)
	for field, value in defaults.items():
		if saved.get(field) in (None, "", "0"):
			frappe.db.set_single_value(SETTINGS, field, value)


# --- Schedule --------------------------------------------------------------------------------------


def is_due(cfg, now=None) -> bool:
	"""True when the automatic report should go out now and has not gone out today."""
	if not cint(cfg.enabled) or not cfg.template or not any(r.enabled for r in cfg.recipients or []):
		return False
	now = get_datetime(now or now_datetime())
	if cfg.last_sent_on and getdate(cfg.last_sent_on) == now.date():
		return False
	if now.time() < get_time(cfg.send_time or "09:00:00"):
		return False
	if cfg.frequency == "Weekly":
		return WEEKDAYS[now.weekday()] == (cfg.weekday or "Monday")
	if cfg.frequency == "Monthly":
		return now.day == min(max(cint(cfg.month_day) or 1, 1), 28)
	return True


def run_scheduled():
	"""Every 15 minutes (hooks.py): send the automatic report when it is due."""
	if not frappe.db.exists("DocType", SETTINGS):
		return
	cfg = frappe.get_single(SETTINGS)
	if not is_due(cfg):
		return
	# mark it first, so a slow or failed run is not sent twice
	frappe.db.set_single_value(SETTINGS, "last_sent_on", now_datetime())
	frappe.db.commit()
	try:
		from_date, to_date = scheduled_period(cfg.frequency or "Weekly")
		send(from_date, to_date, trigger="Scheduled")
	except Exception:
		frappe.db.set_single_value(SETTINGS, "last_result", "Failed: see the Error Log")
		frappe.log_error(title="Pranera CRM: conversion report", message=frappe.get_traceback())


# --- Desk form buttons -----------------------------------------------------------------------------


def _require_manager():
	if not frappe.has_permission(SETTINGS, "write"):
		frappe.throw(_("Only Sales Managers can do this."), frappe.PermissionError)


def _dates(preset: str | None, from_date: str | None, to_date: str | None) -> tuple:
	if preset and preset != "custom":
		return period(preset)
	if not from_date or not to_date:
		frappe.throw(_("Choose the start and end dates."))
	return getdate(from_date), getdate(to_date)


@frappe.whitelist()
def preview(preset: str | None = None, from_date: str | None = None, to_date: str | None = None):
	"""The PDF in the browser, to check before sending."""
	_require_manager()
	data = build(*_dates(preset, from_date, to_date))
	frappe.local.response.filename = file_name(data)
	frappe.local.response.filecontent = render_pdf(data)
	frappe.local.response.type = "pdf"


@frappe.whitelist(methods=["POST"])
def send_now(preset: str | None = None, from_date: str | None = None, to_date: str | None = None) -> dict:
	_require_manager()
	return send(*_dates(preset, from_date, to_date), trigger="Manual")


@frappe.whitelist()
def presets() -> list[dict]:
	return [{"value": k, "label": v} for k, v in PRESETS.items()]
