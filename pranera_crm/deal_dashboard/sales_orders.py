import frappe

from pranera_crm.deal_dashboard.buckets import Buckets
from pranera_crm.deal_dashboard.erpnext_data import (
	SALES_ORDER,
	order_kgs,
	order_sales_persons,
	qualified,
	submitted_orders,
)
from pranera_crm.deal_dashboard.filters import DashboardFilters
from pranera_crm.deal_dashboard.scope import SalesScope

FIELDS = ["name", "customer", "customer_name", "transaction_date", "base_net_total"]


class SalesOrderMetrics:
	"""Requirement 8: submitted Sales Orders made from deals, with their Sales Person."""

	def __init__(self, filters: DashboardFilters, scope: SalesScope):
		self.filters = filters
		self.sales_persons = scope.sales_persons(filters.sales_persons)

	def build(self) -> dict:
		orders = self.rows()
		trend = Buckets(self.filters.granularity, ("orders", "kgs", "value"))
		by_person = {}
		for order in orders:
			trend.add(order["date"], orders=1, kgs=order["kgs"], value=order["value"])
			person = by_person.setdefault(
				order["sales_person"],
				{"sales_person": order["sales_person"], "orders": 0, "kgs": 0.0, "value": 0.0},
			)
			person["orders"] += 1
			person["kgs"] += order["kgs"]
			person["value"] += order["value"]
		return {
			"orders": len(orders),
			"kgs": sum(order["kgs"] for order in orders),
			"value": sum(order["value"] for order in orders),
			"trend": trend.rows(self.filters.from_date, self.filters.to_date),
			"by_sales_person": sorted(by_person.values(), key=lambda row: row["value"], reverse=True),
		}

	def rows(self) -> list[dict]:
		if self.sales_persons == ():
			return []
		headers = self._from_deal_field() | self._from_deal_quotations()
		if not headers:
			return []
		names = list(headers)
		kgs = order_kgs("name", ["name", "in", names])
		persons = order_sales_persons(names)
		return [
			{
				"name": name,
				"label": row.customer_name or row.customer,
				"date": row.transaction_date,
				"value": row.base_net_total or 0.0,
				"kgs": kgs.get(name, 0.0),
				"sales_person": persons.get(name),
				"deal": row.get("deal"),
				"doctype": SALES_ORDER,
			}
			for name, row in sorted(headers.items(), key=lambda item: item[1].transaction_date, reverse=True)
		]

	def _filters(self) -> list:
		filters = [["transaction_date", "between", self.filters.date_range]]
		if self.sales_persons:
			filters.append(["Sales Team", "sales_person", "in", list(self.sales_persons)])
		return qualified(filters)

	def _from_deal_field(self) -> dict:
		if not frappe.get_meta(SALES_ORDER).has_field("custom_crm_deal"):
			return {}
		rows = submitted_orders(
			[
				*(f"`tabSales Order`.{field} as {field}" for field in FIELDS),
				"`tabSales Order`.custom_crm_deal as deal",
			],
			*self._filters(),
			[SALES_ORDER, "custom_crm_deal", "is", "set"],
			group_by="`tabSales Order`.name",
		)
		return {row.name: row for row in rows}

	def _from_deal_quotations(self) -> dict:
		"""Orders made from a Quotation that CRM made from a deal (Quotation.crm_deal)."""
		if not frappe.get_meta("Quotation").has_field("crm_deal"):
			return {}
		quotations = dict(
			frappe.get_list(
				"Quotation",
				fields=["name", "crm_deal"],
				filters={"docstatus": 1, "crm_deal": ["is", "set"]},
				as_list=True,
				limit_page_length=0,
			)
		)
		if not quotations:
			return {}
		rows = submitted_orders(
			[
				*(f"`tabSales Order`.{field} as {field}" for field in FIELDS),
				"`tabSales Order Item`.prevdoc_docname as quotation",
			],
			*self._filters(),
			["Sales Order Item", "prevdoc_docname", "in", list(quotations)],
			# get_list refuses MAX() on a joined table's column: one row per order and quotation
			group_by="`tabSales Order`.name, `tabSales Order Item`.prevdoc_docname",
		)
		for row in rows:
			row.deal = quotations.get(row.quotation)
		return {row.name: row for row in rows}
