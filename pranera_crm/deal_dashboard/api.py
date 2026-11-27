import frappe
from crm.utils import sales_user_only
from frappe.utils import cint
from frappe.utils.caching import redis_cache

from pranera_crm.deal_dashboard.customers import CustomerMetrics
from pranera_crm.deal_dashboard.deals import DealMetrics
from pranera_crm.deal_dashboard.filters import DashboardFilters
from pranera_crm.deal_dashboard.rows import Rows
from pranera_crm.deal_dashboard.sales_orders import SalesOrderMetrics
from pranera_crm.deal_dashboard.scope import SalesScope

CACHE_VERSION_KEY = "pranera_deal_dashboard_version"
CACHE_SECONDS = 60
SECTIONS = {"customers": CustomerMetrics, "deals": DealMetrics, "sales_orders": SalesOrderMetrics}


@frappe.whitelist(methods=["GET"])
@sales_user_only
def get_section(
	section: str,
	from_date: str,
	to_date: str,
	granularity: str = "day",
	sales_persons: str | None = None,
	territory: str | None = None,
) -> dict:
	"""One section of the Deal Dashboard: customers, deals or sales_orders."""
	if section not in SECTIONS:
		frappe.throw(frappe._("Section {0} is not part of the Deal Dashboard").format(section))
	frappe.has_permission("CRM Deal", "read", throw=True)
	filters = DashboardFilters.build(from_date, to_date, granularity, sales_persons, territory)
	return _cached_section(section, frappe.session.user, _cache_version(), filters.cache_key())


@frappe.whitelist(methods=["GET"])
@sales_user_only
def get_rows(
	segment: str,
	from_date: str,
	to_date: str,
	granularity: str = "day",
	sales_persons: str | None = None,
	territory: str | None = None,
	value: str | None = None,
	sort: str = "date",
	descending: int = 1,
	start: int = 0,
	page_length: int = 20,
) -> dict:
	"""The records behind one number of the dashboard."""
	frappe.has_permission("CRM Deal", "read", throw=True)
	filters = DashboardFilters.build(from_date, to_date, granularity, sales_persons, territory)
	rows = Rows(filters, SalesScope(), segment, value)
	return rows.page(sort, bool(cint(descending)), start, page_length)


@frappe.whitelist(methods=["GET"])
@sales_user_only
def get_filter_options() -> dict:
	"""The Sales Persons the user may pick (their own and those below), and the CRM territories."""
	frappe.has_permission("CRM Deal", "read", throw=True)
	scope = SalesScope()
	filters = {"enabled": 1}
	if scope.allowed is not None:
		filters["name"] = ["in", list(scope.allowed) or [""]]
	return {
		"sales_persons": frappe.get_list(
			"Sales Person", filters=filters, pluck="name", order_by="lft asc", limit_page_length=0
		),
		"territories": frappe.get_list(
			"CRM Territory", pluck="name", order_by="lft asc", limit_page_length=0
		),
		"own_sales_person": scope.user_sales_person,
		"sees_all": scope.sees_all,
	}


def bump_cache_version(doc=None, method=None):
	"""Deal, organization, customer and order changes: cached sections are stale once this commits."""
	frappe.db.after_commit.add(_set_new_cache_version)


def _set_new_cache_version():
	frappe.cache.set_value(CACHE_VERSION_KEY, frappe.generate_hash(length=8))


def _cache_version() -> str:
	return frappe.cache.get_value(CACHE_VERSION_KEY) or ""


@redis_cache(ttl=CACHE_SECONDS)
def _cached_section(section: str, user: str, version: str, filters_key: tuple) -> dict:
	# `user` and `version` only make the key: the numbers differ per user and per saved record
	filters = DashboardFilters.build(*filters_key)
	return SECTIONS[section](filters, SalesScope(user)).build()
