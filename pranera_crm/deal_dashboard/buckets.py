from datetime import date, timedelta

from frappe.utils import add_months, add_years, getdate


class Buckets:
	"""Sums by day, week, month or year, with the empty ones in between filled in."""

	def __init__(self, unit: str, measures: tuple[str, ...]):
		self.unit = unit
		self.measures = measures
		self.sums = {}

	def add(self, day: date, **amounts):
		bucket = self.sums.setdefault(self.start(getdate(day)), dict.fromkeys(self.measures, 0))
		for measure, amount in amounts.items():
			bucket[measure] += amount

	def rows(self, first: date | None = None, last: date | None = None) -> list[dict]:
		"""Every bucket from `first` to `last` (or from the first to the last one with data)."""
		if not self.sums and not (first and last):
			return []
		start = self.start(getdate(first)) if first else min(self.sums)
		end = self.start(getdate(last)) if last else max(self.sums)
		rows = []
		while start <= end:
			rows.append({"period": str(start), **self.sums.get(start, dict.fromkeys(self.measures, 0))})
			start = self.next(start)
		return rows

	def start(self, day: date) -> date:
		if self.unit == "year":
			return day.replace(month=1, day=1)
		if self.unit == "month":
			return day.replace(day=1)
		if self.unit == "week":
			return day - timedelta(days=day.weekday())
		return day

	def next(self, start: date) -> date:
		if self.unit == "year":
			return getdate(add_years(start, 1))
		if self.unit == "month":
			return getdate(add_months(start, 1))
		return start + timedelta(days=7 if self.unit == "week" else 1)
