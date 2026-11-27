from functools import cached_property

import frappe

from pranera_crm.deal_dashboard.filters import DashboardFilters, territory_with_children
from pranera_crm.deal_dashboard.kgs import DealLineKgs, line_fields, line_group_by
from pranera_crm.deal_dashboard.scope import SalesScope, has_deal_sales_person_field

DEAL = "CRM Deal"
LOG = "CRM Status Change Log"
DELIVERED = "Delivered"
OPEN_TYPES = ("Open", "Ongoing", "On Hold")


class Stages:
	"""The CRM Deal Status master, in pipeline order."""

	def __init__(self):
		self.rows = frappe.get_all(
			"CRM Deal Status",
			fields=["name", "type", "color", "position"],
			order_by="position asc, name asc",
		)

	def names(self, *types: str) -> list[str]:
		return [row.name for row in self.rows if row.type in types]

	@property
	def open(self) -> list[str]:
		return self.names(*OPEN_TYPES)

	@property
	def won(self) -> list[str]:
		return self.names("Won")

	@property
	def lost(self) -> list[str]:
		return self.names("Lost")

	@property
	def path(self) -> list[str]:
		"""The forward path a deal moves along: open, ongoing and won stages, not On Hold or Lost."""
		return self.names("Open", "Ongoing", "Won")


class DealQuery:
	"""get_list on CRM Deal with the dashboard's Sales Person and Territory filters.

	Read with the user's permissions, so CRM's own rule decides which deals count.
	"""

	def __init__(self, filters: DashboardFilters, scope: SalesScope):
		self.filters = filters
		self.scope = scope
		self.stages = Stages()

	@cached_property
	def base(self) -> tuple[list, list]:
		filters, or_filters = self.scope.deal_filters(self.filters.sales_persons)
		if self.filters.territory:
			filters.append(["territory", "in", territory_with_children(self.filters.territory)])
		return filters, or_filters

	def get_list(self, fields: list[str], *extra: list, child: bool = False, **kwargs) -> list[dict]:
		"""`child`: the query joins a child table, so every filter names CRM Deal."""
		filters, or_filters = self.base
		filters = [*filters, *extra]
		if child:
			filters = [_qualified(condition) for condition in filters]
			or_filters = [_qualified(condition) for condition in or_filters]
		kwargs.setdefault("limit_page_length", 0)
		return frappe.get_list(DEAL, fields=fields, filters=filters, or_filters=or_filters, **kwargs)

	def owner_group(self) -> list[str]:
		"""The CRM Deal fields a deal's Sales Person comes from."""
		return ["deal_owner", "custom_sales_person"] if has_deal_sales_person_field() else ["deal_owner"]

	def fields(self, group: list[str]) -> list[str]:
		return [f"`tabCRM Deal`.{field} as {field}" for field in group]

	def group_by(self, group: list[str]) -> str:
		return ", ".join(f"`tabCRM Deal`.{field}" for field in group)

	def sales_person(self, row: dict) -> str | None:
		return self.scope.deal_sales_person(row.get("deal_owner"), row.get("custom_sales_person"))

	def line_kgs(self, group: list[str], *extra: list) -> list[dict]:
		"""Kilograms per `group` (CRM Deal fields): rows with the group values, kgs and not_in_kgs lines."""
		group_by = ", ".join(part for part in (self.group_by(group), line_group_by()) if part)
		rows = self.get_list([*self.fields(group), *line_fields()], *extra, child=True, group_by=group_by)
		converter = DealLineKgs(rows)
		totals = {}
		for row in rows:
			key = tuple(row.get(field) for field in group)
			total = totals.setdefault(
				key, {**dict(zip(group, key, strict=True)), "kgs": 0.0, "not_in_kgs": 0}
			)
			kgs = converter.kgs(row)
			if kgs is None:
				total["not_in_kgs"] += row.line_count
			else:
				total["kgs"] += kgs
		return list(totals.values())


def _qualified(condition: list) -> list:
	return condition if len(condition) == 4 else [DEAL, *condition]
