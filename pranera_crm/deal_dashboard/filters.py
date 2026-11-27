import json
from dataclasses import dataclass, replace
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, add_years, date_diff, getdate

GRANULARITIES = ("day", "week", "month", "year")


@dataclass(frozen=True)
class DashboardFilters:
	"""The dashboard's global filters, checked once."""

	from_date: date
	to_date: date
	granularity: str = "day"
	sales_persons: tuple[str, ...] = ()
	territory: str | None = None

	@classmethod
	def build(
		cls,
		from_date: str,
		to_date: str,
		granularity: str = "day",
		sales_persons: str | list | tuple | None = None,
		territory: str | None = None,
	) -> "DashboardFilters":
		if granularity not in GRANULARITIES:
			frappe.throw(_("Granularity {0} is not one of {1}").format(granularity, ", ".join(GRANULARITIES)))
		start, end = getdate(from_date), getdate(to_date)
		if not start or not end:
			frappe.throw(_("From Date and To Date are required"))
		if end < start:
			frappe.throw(_("To Date {0} is before From Date {1}").format(end, start))
		return cls(start, end, granularity, _sales_person_list(sales_persons), territory or None)

	def previous(self) -> "DashboardFilters":
		"""The period of the same length that ends the day before this one starts."""
		days = date_diff(self.to_date, self.from_date) + 1
		return replace(
			self,
			from_date=getdate(add_days(self.from_date, -days)),
			to_date=getdate(add_days(self.from_date, -1)),
		)

	def last_year(self) -> "DashboardFilters":
		return replace(
			self,
			from_date=getdate(add_years(self.from_date, -1)),
			to_date=getdate(add_years(self.to_date, -1)),
		)

	@property
	def date_range(self) -> list:
		return [self.from_date, self.to_date]

	def cache_key(self) -> tuple:
		return (
			str(self.from_date),
			str(self.to_date),
			self.granularity,
			self.sales_persons,  # a tuple: the cache key must be hashable
			self.territory,
		)


def _sales_person_list(value: str | list | tuple | None) -> tuple[str, ...]:
	"""A JSON list (from a GET query) or a list of Sales Person names; nothing else."""
	if not value:
		return ()
	if isinstance(value, tuple):
		value = list(value)
	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			value = [value]
	if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
		frappe.throw(_("Sales Persons must be a list of names"))
	return tuple(sorted(set(value)))


def territory_with_children(territory: str) -> list[str]:
	bounds = frappe.db.get_value("CRM Territory", territory, ["lft", "rgt"], as_dict=True)
	if not bounds:
		frappe.throw(_("Territory {0} not found").format(territory))
	return frappe.get_list(
		"CRM Territory",
		filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
		pluck="name",
		limit_page_length=0,
	)
