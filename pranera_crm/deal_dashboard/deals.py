from frappe.utils import flt, get_datetime, getdate

from pranera_crm.deal_dashboard.buckets import Buckets
from pranera_crm.deal_dashboard.deal_base import DELIVERED, LOG, DealQuery

COUNT = "count(distinct `tabCRM Deal`.name) as deals"


class DealMetrics(DealQuery):
	"""Requirements 4 to 7: pipeline Kgs, delivered Kgs, their comparison and stage conversion."""

	def build(self) -> dict:
		return {
			"pipeline": self.pipeline(),
			"delivered": self.delivered(),
			"conversion": self.conversion(),
		}

	# ---- 4. pipeline ----

	def pipeline(self) -> dict:
		"""Deals not yet won or lost, as they are now: the period does not apply."""
		group = ["status", *self.owner_group()]
		open_stage = ["status", "in", self.stages.open]
		kgs = self.line_kgs(group, open_stage)
		counts = self.get_list([*self.fields(group), COUNT], open_stage, group_by=self.group_by(group))

		by_stage = {name: {"status": name, "deals": 0, "kgs": 0.0} for name in self.stages.open}
		by_person = {}
		for row in counts:
			by_stage[row.status]["deals"] += row.deals
			self._person(by_person, row)["deals"] += row.deals
		for row in kgs:
			by_stage[row["status"]]["kgs"] += row["kgs"]
			self._person(by_person, row)["kgs"] += row["kgs"]

		colors = {stage.name: stage.color for stage in self.stages.rows}
		return {
			"kgs": sum(row["kgs"] for row in kgs),
			"deals": sum(row.deals for row in counts),
			"not_in_kgs": sum(row["not_in_kgs"] for row in kgs),
			"by_stage": [{**stage, "color": colors.get(stage["status"])} for stage in by_stage.values()],
			"by_sales_person": sorted(by_person.values(), key=lambda row: row["kgs"], reverse=True),
		}

	def _person(self, totals: dict, row: dict) -> dict:
		person = self.sales_person(row)
		return totals.setdefault(person, {"sales_person": person, "deals": 0, "kgs": 0.0})

	# ---- 5 and 6. delivered ----

	def delivered(self) -> dict:
		periods = {
			"current": self.filters,
			"previous": self.filters.previous(),
			"last_year": self.filters.last_year(),
		}
		deals = self.delivered_deals(min(period.from_date for period in periods.values()))
		totals = {key: _total(deals, period.from_date, period.to_date) for key, period in periods.items()}
		trend = Buckets(self.filters.granularity, ("kgs", "deals"))
		for deal in deals:
			if self.filters.from_date <= deal["delivered_on"] <= self.filters.to_date:
				trend.add(deal["delivered_on"], kgs=deal["kgs"], deals=1)
		for key, period in periods.items():
			totals[key].update({"from": str(period.from_date), "to": str(period.to_date)})
		return {
			"unit": self.filters.granularity,
			"trend": trend.rows(self.filters.from_date, self.filters.to_date),
			"comparison": {
				**totals,
				"vs_previous": _change(totals["current"]["kgs"], totals["previous"]["kgs"]),
				"vs_last_year": _change(totals["current"]["kgs"], totals["last_year"]["kgs"]),
			},
		}

	def delivered_deals(self, since) -> list[dict]:
		"""Delivered deals with the day they became Delivered and their Kgs.

		The day comes from the status log: when the current Delivered status began. A deal
		created as Delivered began there on its creation day. Becoming Delivered modifies
		the deal, so one delivered since `since` was modified since then.
		"""
		candidates = self.get_list(
			["name", "closed_date", "modified"],
			["status", "=", DELIVERED],
			["modified", ">=", since],
		)
		if not candidates:
			return []
		names = [deal.name for deal in candidates]
		began = self._delivered_since(names)
		kgs = {row["name"]: row for row in self.line_kgs(["name"], ["name", "in", names])}
		deals = []
		for deal in candidates:
			day = getdate(began.get(deal.name) or deal.closed_date or deal.modified)
			line = kgs.get(deal.name, {})
			deals.append({"name": deal.name, "delivered_on": day, "kgs": line.get("kgs", 0.0)})
		return deals

	def _delivered_since(self, names: list[str]) -> dict:
		rows = self.get_list(
			["`tabCRM Deal`.name as name", f"`tab{LOG}`.from_date as began"],
			["name", "in", names],
			[LOG, "from", "=", DELIVERED],
			[LOG, "to", "is", "not set"],
			child=True,
		)
		began = {}
		for row in rows:
			if row.began and (row.name not in began or get_datetime(row.began) > began[row.name]):
				began[row.name] = get_datetime(row.began)
		return began

	# ---- 7. conversion ----

	def conversion(self) -> dict:
		"""Deals created in the period: how far each got along the stage path, and the win rate."""
		created = ["creation", "between", [self.filters.from_date, f"{self.filters.to_date} 23:59:59.999999"]]
		deals = self.get_list(["name", "status"], created)
		history = self.get_list(
			["`tabCRM Deal`.name as name", f"`tab{LOG}`.`from` as stage"],
			created,
			child=True,
			group_by=f"`tabCRM Deal`.name, `tab{LOG}`.`from`",
		)
		path = self.stages.path
		position = {name: index for index, name in enumerate(path)}
		furthest = {deal.name: position.get(deal.status, -1) for deal in deals}
		for row in history:
			if row.name in furthest:
				furthest[row.name] = max(furthest[row.name], position.get(row.stage, -1))

		reached = [sum(1 for reach in furthest.values() if reach >= index) for index in range(len(path))]
		won = sum(1 for deal in deals if deal.status in self.stages.won)
		lost = sum(1 for deal in deals if deal.status in self.stages.lost)
		return {
			"deals": len(deals),
			"won": won,
			"lost": lost,
			"win_rate": flt(won / (won + lost) * 100, 1) if won + lost else None,
			"stages": [
				{
					"stage": stage,
					"reached": reached[index],
					"next_rate": _rate(reached, index),
				}
				for index, stage in enumerate(path)
			],
		}


def _total(deals: list[dict], start, end) -> dict:
	inside = [deal for deal in deals if start <= deal["delivered_on"] <= end]
	return {"kgs": sum(deal["kgs"] for deal in inside), "deals": len(inside)}


def _change(now: float, before: float) -> dict:
	return {"kg": now - before, "pct": flt((now - before) / before * 100, 1) if before else None}


def _rate(reached: list[int], index: int) -> float | None:
	if index + 1 >= len(reached) or not reached[index]:
		return None
	return flt(reached[index + 1] / reached[index] * 100, 1)
