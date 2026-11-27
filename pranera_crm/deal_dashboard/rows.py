import frappe
from frappe import _
from frappe.utils import getdate

from pranera_crm.deal_dashboard.buckets import Buckets
from pranera_crm.deal_dashboard.customers import GROUPS, CustomerMetrics
from pranera_crm.deal_dashboard.deal_base import DealQuery
from pranera_crm.deal_dashboard.deals import DealMetrics
from pranera_crm.deal_dashboard.filters import DashboardFilters
from pranera_crm.deal_dashboard.sales_orders import SalesOrderMetrics
from pranera_crm.deal_dashboard.scope import SalesScope

# `value` that picks rows with no Sales Person
NO_SALES_PERSON = "__none__"
DEAL_SEGMENTS = ("pipeline", "pipeline_person", "delivered")
SEGMENTS = (*GROUPS, *DEAL_SEGMENTS, "sales_orders")
SORT_KEYS = ("label", "sales_person", "date", "kgs", "value", "status")
MAX_PAGE_LENGTH = 100


class Rows:
	"""The records behind one number of the dashboard, sorted, a page at a time."""

	def __init__(self, filters: DashboardFilters, scope: SalesScope, segment: str, value: str | None = None):
		if segment not in SEGMENTS:
			frappe.throw(_("Segment {0} is not a list of the Deal Dashboard").format(segment))
		self.filters = filters
		self.scope = scope
		self.segment = segment
		self.value = value or None

	def page(
		self, sort: str = "date", descending: bool = True, start: int = 0, page_length: int = 20
	) -> dict:
		if sort not in SORT_KEYS:
			frappe.throw(_("Cannot sort by {0}").format(sort))
		rows = self._rows()
		rows.sort(key=lambda row: _sort_value(row.get(sort)), reverse=descending)
		start = max(start, 0)
		end = start + min(max(page_length, 1), MAX_PAGE_LENGTH)
		page = rows[start:end]
		if self.segment in DEAL_SEGMENTS:
			self._add_deal_kgs(page)
		return {"rows": page, "total": len(rows)}

	def _rows(self) -> list[dict]:
		if self.segment in GROUPS:
			rows = CustomerMetrics(self.filters, self.scope).rows(self.segment)
			return self._of_sales_person(rows)
		if self.segment == "sales_orders":
			return self._in_bucket(self._of_sales_person(SalesOrderMetrics(self.filters, self.scope).rows()))
		if self.segment == "delivered":
			return self._in_bucket(self._delivered())
		return self._pipeline()

	def _of_sales_person(self, rows: list[dict]) -> list[dict]:
		if self.segment not in (*GROUPS, "sales_orders", "pipeline_person") or not self.value:
			return rows
		wanted = None if self.value == NO_SALES_PERSON else self.value
		return [row for row in rows if row["sales_person"] == wanted]

	def _in_bucket(self, rows: list[dict]) -> list[dict]:
		"""`value`: the first day of a trend bar, for the rows of that bar only."""
		if not self.value or self.segment not in ("delivered", "sales_orders"):
			return rows
		buckets = Buckets(self.filters.granularity, ())
		start = getdate(self.value)
		return [row for row in rows if buckets.start(getdate(row["date"])) == start]

	def _pipeline(self) -> list[dict]:
		query = DealQuery(self.filters, self.scope)
		stage = self.value if self.segment == "pipeline" and self.value else None
		if stage and stage not in query.stages.open:
			frappe.throw(_("{0} is not an open stage").format(stage))
		statuses = [stage] if stage else query.stages.open
		deals = query.get_list(
			["name", "organization", "status", "modified", *query.owner_group()], ["status", "in", statuses]
		)
		rows = [_deal_row(query, deal, deal.modified) for deal in deals]
		return self._of_sales_person(rows)

	def _delivered(self) -> list[dict]:
		metrics = DealMetrics(self.filters, self.scope)
		delivered = {
			deal["name"]: deal
			for deal in metrics.delivered_deals(self.filters.from_date)
			if self.filters.from_date <= deal["delivered_on"] <= self.filters.to_date
		}
		if not delivered:
			return []
		deals = metrics.get_list(
			["name", "organization", "status", *metrics.owner_group()], ["name", "in", list(delivered)]
		)
		return [_deal_row(metrics, deal, delivered[deal.name]["delivered_on"]) for deal in deals]

	def _add_deal_kgs(self, page: list[dict]):
		if not page:
			return
		query = DealQuery(self.filters, self.scope)
		kgs = {
			row["name"]: row
			for row in query.line_kgs(["name"], ["name", "in", [row["name"] for row in page]])
		}
		for row in page:
			row["kgs"] = kgs.get(row["name"], {}).get("kgs", 0.0)
			row["not_in_kgs"] = kgs.get(row["name"], {}).get("not_in_kgs", 0)


def _deal_row(query: DealQuery, deal: dict, day) -> dict:
	return {
		"name": deal.name,
		"label": deal.organization or deal.name,
		"status": deal.status,
		"sales_person": query.sales_person(deal),
		"date": str(getdate(day)),
		"doctype": "CRM Deal",
	}


def _sort_value(value):
	"""None sorts as the smallest value of any type."""
	return (value is not None, value if not isinstance(value, str) else value.casefold())
