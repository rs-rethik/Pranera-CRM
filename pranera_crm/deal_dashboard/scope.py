import frappe
from frappe.utils.caching import redis_cache

# these roles see every Sales Person's numbers
ALL_ACCESS_ROLES = ("System Manager", "Sales Manager")


class SalesScope:
	"""Whose numbers the current user may see, and how users map to Sales Persons.

	Deals are read with frappe.get_list, so CRM's own rule decides which deals a user
	sees. Customers and Sales Orders carry no such rule in ERPNext, so they are limited
	here to the user's Sales Person and the Sales Persons below it in the tree.
	"""

	def __init__(self, user: str | None = None):
		self.user = user or frappe.session.user
		self.user_sales_person = user_sales_persons().get(self.user)
		self.sees_all = self.user == "Administrator" or bool(
			set(frappe.get_roles(self.user)) & set(ALL_ACCESS_ROLES)
		)

	@property
	def allowed(self) -> tuple[str, ...] | None:
		"""Sales Persons the user may see; None means all of them."""
		if self.sees_all:
			return None
		if not self.user_sales_person:
			return ()
		return tuple(sales_person_subtree(self.user_sales_person))

	def sales_persons(self, selected: tuple[str, ...]) -> tuple[str, ...] | None:
		"""The Sales Persons a customer or order widget covers; None means no limit."""
		selected = with_subtrees(selected)
		allowed = self.allowed
		if allowed is None:
			return selected or None
		if not selected:
			return allowed
		return tuple(name for name in selected if name in allowed)

	def deal_filters(self, selected: tuple[str, ...]) -> tuple[list, list]:
		"""(filters, or_filters) that keep the deals of the selected Sales Persons.

		A deal belongs to its owner's Sales Person; the deal's own Sales Person field
		counts only when the owner is not linked to one (that field goes stale).
		"""
		if not selected:
			return [], []
		selected = with_subtrees(selected)
		mapping = user_sales_persons()
		chosen_users = [user for user, person in mapping.items() if person in selected]
		other_users = [user for user, person in mapping.items() if person not in selected]
		filters = [["deal_owner", "not in", other_users]] if other_users else []
		or_filters = [["deal_owner", "in", chosen_users or [""]]]
		if has_deal_sales_person_field():
			or_filters.append(["custom_sales_person", "in", list(selected)])
		return filters, or_filters

	def deal_sales_person(self, owner: str | None, field_value: str | None) -> str | None:
		return user_sales_persons().get(owner) or field_value or None


def has_deal_sales_person_field() -> bool:
	return frappe.get_meta("CRM Deal").has_field("custom_sales_person")


@redis_cache(ttl=300)
def user_sales_persons() -> dict[str, str]:
	"""{user: Sales Person}, through Sales Person → Employee → User; the first enabled one wins.

	Read without the user's permissions: it only tells whose numbers are whose.
	"""
	employees = dict(
		frappe.get_all(
			"Employee", filters={"user_id": ["is", "set"]}, fields=["name", "user_id"], as_list=True
		)
	)
	mapping = {}
	persons = frappe.get_all(
		"Sales Person",
		filters={"enabled": 1, "employee": ["is", "set"]},
		fields=["name", "employee"],
		order_by="lft asc",
	)
	for person in persons:
		user = employees.get(person.employee)
		if user and user not in mapping:
			mapping[user] = person.name
	return mapping


def with_subtrees(selected: tuple[str, ...]) -> tuple[str, ...]:
	"""A picked group stands for everyone below it in the Sales Person tree."""
	names = set()
	for name in selected:
		names.update(sales_person_subtree(name) or [name])
	return tuple(sorted(names))


def sales_person_subtree(sales_person: str) -> list[str]:
	bounds = frappe.db.get_value("Sales Person", sales_person, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return []
	return frappe.get_all(
		"Sales Person",
		filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]},
		pluck="name",
	)


def clear_cache(doc=None, method=None):
	"""Employee / Sales Person changes move numbers between Sales Persons."""
	user_sales_persons.clear_cache()
