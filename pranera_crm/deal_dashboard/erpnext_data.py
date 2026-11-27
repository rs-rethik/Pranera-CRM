import frappe
from frappe.utils import flt

from pranera_crm.deal_dashboard.kgs import KgsConverter

SALES_ORDER = "Sales Order"


def submitted_orders(fields: list[str], *filters: list, **kwargs) -> list[dict]:
	"""Submitted Sales Orders read with the user's permissions."""
	kwargs.setdefault("limit_page_length", 0)
	return frappe.get_list(SALES_ORDER, fields=fields, filters=[["docstatus", "=", 1], *filters], **kwargs)


def customer_sales_persons(customers: list[str]) -> dict[str, str | None]:
	"""{customer: the first Sales Person in its Sales Team}, for customers the user can read."""
	if not customers:
		return {}
	rows = frappe.get_list(
		"Customer",
		fields=["name", "`tabSales Team`.sales_person as sales_person"],
		filters={"name": ["in", customers]},
		order_by="`tabSales Team`.idx asc",
		limit_page_length=0,
	)
	persons = {}
	for row in rows:
		if not persons.get(row.name):
			persons[row.name] = row.sales_person
	return persons


def order_sales_persons(orders: list[str]) -> dict[str, str | None]:
	"""{Sales Order: the first Sales Person in its Sales Team}."""
	if not orders:
		return {}
	rows = frappe.get_list(
		SALES_ORDER,
		fields=["name", "`tabSales Team`.sales_person as sales_person"],
		filters={"name": ["in", orders]},
		order_by="`tabSales Team`.idx asc",
		limit_page_length=0,
	)
	persons = {}
	for row in rows:
		if not persons.get(row.name):
			persons[row.name] = row.sales_person
	return persons


def order_kgs(group: str, *filters: list) -> dict:
	"""{value of `group` (a Sales Order field): kilograms of its submitted orders' rows}."""
	rows = submitted_orders(
		[
			f"`tabSales Order`.{group} as grp",
			"`tabSales Order Item`.item_code as item",
			"`tabSales Order Item`.stock_uom as uom",
			"sum(`tabSales Order Item`.stock_qty) as qty",
		],
		*filters,
		group_by=f"`tabSales Order`.{group}, `tabSales Order Item`.item_code, `tabSales Order Item`.stock_uom",
	)
	converter = KgsConverter({row.item for row in rows})
	totals = {}
	for row in rows:
		kgs = converter.convert(row.qty, row.uom, row.item)
		if kgs is not None:
			totals[row.grp] = totals.get(row.grp, 0.0) + flt(kgs)
	return totals


def qualified(filters: list) -> list:
	"""Name Sales Order in each filter, for queries that join its child tables."""
	return [condition if len(condition) == 4 else [SALES_ORDER, *condition] for condition in filters]
