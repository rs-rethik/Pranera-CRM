from frappe.utils import add_days

from pranera_crm.deal_dashboard.deal_base import DealQuery
from pranera_crm.deal_dashboard.erpnext_data import customer_sales_persons, order_kgs, submitted_orders
from pranera_crm.deal_dashboard.filters import DashboardFilters
from pranera_crm.deal_dashboard.scope import SalesScope

ACTIVE_DAYS = 180
GROUPS = ("active", "new", "potential")


class CustomerMetrics:
	"""Requirements 1 to 3: active, newly acquired and potential customers with their Sales Person."""

	def __init__(self, filters: DashboardFilters, scope: SalesScope):
		self.filters = filters
		self.scope = scope
		self.sales_persons = scope.sales_persons(filters.sales_persons)

	def build(self) -> dict:
		# the cards and the table need counts only; Kgs are read for a drill-down list
		groups = {group: getattr(self, group)(with_kgs=False) for group in GROUPS}
		by_person = {}
		for group, rows in groups.items():
			for row in rows:
				person = by_person.setdefault(
					row["sales_person"], {"sales_person": row["sales_person"], **dict.fromkeys(GROUPS, 0)}
				)
				person[group] += 1
		return {
			"active_since": str(self.active_since),
			**{group: {"count": len(rows)} for group, rows in groups.items()},
			"by_sales_person": sorted(by_person.values(), key=lambda row: row["active"], reverse=True),
		}

	def rows(self, group: str) -> list[dict]:
		return getattr(self, group)()

	@property
	def active_since(self):
		return add_days(self.filters.to_date, -(ACTIVE_DAYS - 1))

	def active(self, with_kgs: bool = True) -> list[dict]:
		"""Customers with a submitted Sales Order in the 180 days up to the end of the period."""
		window = ["transaction_date", "between", [self.active_since, self.filters.to_date]]
		return self._customers([window], with_kgs)

	def new(self, with_kgs: bool = True) -> list[dict]:
		"""Customers whose first ever submitted Sales Order is in the period."""
		period = ["transaction_date", "between", self.filters.date_range]
		ordered = [row.customer for row in submitted_orders(["customer"], period, group_by="customer")]
		if not ordered:
			return []
		first = submitted_orders(
			["customer", "min(transaction_date) as first_order"],
			["customer", "in", ordered],
			group_by="customer",
		)
		new = [
			row.customer for row in first if self.filters.from_date <= row.first_order <= self.filters.to_date
		]
		return self._customers([["customer", "in", new or [""]], period], with_kgs)

	def _customers(self, filters: list[list], with_kgs: bool) -> list[dict]:
		"""Customers with submitted orders matching `filters`: last order date and ordered Kgs."""
		orders = submitted_orders(
			["customer", "max(customer_name) as customer_name", "max(transaction_date) as last_order"],
			*filters,
			group_by="customer",
		)
		persons = customer_sales_persons([row.customer for row in orders])
		kgs = order_kgs("customer", *filters) if with_kgs else {}
		rows = []
		for row in orders:
			person = persons.get(row.customer)
			if self._covers(person):
				rows.append(
					{
						"name": row.customer,
						"label": row.customer_name or row.customer,
						"sales_person": person,
						"date": str(row.last_order),
						"kgs": kgs.get(row.customer, 0.0),
						"doctype": "Customer",
					}
				)
		return rows

	def _covers(self, person: str | None) -> bool:
		if self.sales_persons is None:
			return True
		return person in self.sales_persons

	def potential(self, with_kgs: bool = True) -> list[dict]:
		"""CRM Organizations with an open deal whose customer has no submitted Sales Order."""
		return PotentialCustomers(self.filters, self.scope).rows(with_kgs)


class PotentialCustomers(DealQuery):
	def rows(self, with_kgs: bool = True) -> list[dict]:
		open_stage = ["status", "in", self.stages.open]
		group = ["organization", *self.owner_group()]
		deals = self.get_list(
			[*self.fields(group), "max(creation) as last_deal", *self._customer_field()],
			open_stage,
			["organization", "is", "set"],
			group_by=self.group_by(group),
		)
		latest = {}
		for row in deals:
			if row.organization not in latest or row.last_deal > latest[row.organization].last_deal:
				latest[row.organization] = row
		ordering = self._ordering_customers(latest)
		kgs = {}
		if with_kgs:
			kgs = {row["organization"]: row["kgs"] for row in self.line_kgs(["organization"], open_stage)}
		return [
			{
				"name": org,
				"label": org,
				"sales_person": self.sales_person(row),
				"date": str(row.last_deal.date()),
				"kgs": kgs.get(org, 0.0),
				"doctype": "CRM Organization",
			}
			for org, row in latest.items()
			if org not in ordering
		]

	def _customer_field(self) -> list[str]:
		from frappe import get_meta

		return (
			["max(custom_customer) as customer"] if get_meta("CRM Deal").has_field("custom_customer") else []
		)

	def _ordering_customers(self, latest: dict) -> set[str]:
		"""Organizations whose customer already has a submitted Sales Order."""
		from frappe import get_all, get_meta

		customer_of = {org: row.get("customer") for org, row in latest.items() if row.get("customer")}
		if get_meta("CRM Organization").has_field("custom_customer"):
			# the organization's own link; read for every listed organization, the deals are the user's
			for org, customer in get_all(
				"CRM Organization",
				filters={"name": ["in", list(latest)], "custom_customer": ["is", "set"]},
				fields=["name", "custom_customer"],
				as_list=True,
			):
				customer_of.setdefault(org, customer)
		customers = list(set(customer_of.values()))
		if not customers:
			return set()
		ordered = {
			row.customer
			for row in submitted_orders(["customer"], ["customer", "in", customers], group_by="customer")
		}
		return {org for org, customer in customer_of.items() if customer in ordered}
