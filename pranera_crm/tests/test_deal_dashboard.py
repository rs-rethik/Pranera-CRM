import frappe
from crm.tests import CRMTestCase
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate, nowdate

from pranera_crm.deal_dashboard import api
from pranera_crm.deal_dashboard.customers import CustomerMetrics
from pranera_crm.deal_dashboard.deals import DealMetrics, _change
from pranera_crm.deal_dashboard.filters import DashboardFilters
from pranera_crm.deal_dashboard.kgs import KgsConverter
from pranera_crm.deal_dashboard.rows import Rows
from pranera_crm.deal_dashboard.sales_orders import SalesOrderMetrics
from pranera_crm.deal_dashboard.scope import SalesScope, user_sales_persons

# every test deal is in this territory, so the site's own deals never reach the numbers
TERRITORY = "ZZT Dashboard Region"
COMPANY = "_Test Company"
CUSTOMER_GROUP = "ZZT Dashboard Customers"
MANAGER = "zzt.dash.manager@example.com"
REP, OTHER_REP = "zzt.dash.rep@example.com", "zzt.dash.rep2@example.com"
LEAD_PERSON, REP_PERSON, OTHER_PERSON = "ZZT Head", "ZZT Rep", "ZZT Rep Two"
KG_ITEM, PCS_ITEM, CONE_ITEM = "ZZT-FABRIC-KG", "ZZT-COLLAR-PCS", "ZZT-YARN-CONE"
STAGES = [
	("ZZT Requirement", "Open"),
	("ZZT Quotation Sent", "Ongoing"),
	("ZZT Awaiting PO", "Ongoing"),
	("Order Confirmed", "Won"),
	("Dispatched", "Won"),
	("Delivered", "Won"),
	("On Hold", "On Hold"),
	("Lost", "Lost"),
]


class TestDealDashboard(CRMTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.today = getdate(nowdate())
		for position, (name, stage_type) in enumerate(STAGES, start=100):
			ensure("CRM Deal Status", name, deal_status=name, type=stage_type, position=position)
			# the site may have these stages already: put them after its own, in this order
			frappe.db.set_value("CRM Deal Status", name, {"type": stage_type, "position": position})
		ensure("CRM Territory", TERRITORY, territory_name=TERRITORY)
		ensure("CRM Lost Reason", "ZZT Price", lost_reason="ZZT Price")
		ensure(
			"Customer Group",
			CUSTOMER_GROUP,
			customer_group_name=CUSTOMER_GROUP,
			parent_customer_group="All Customer Groups",
		)
		make_item(KG_ITEM, "Kg")
		make_item(PCS_ITEM, "Nos")
		make_item(CONE_ITEM, "Nos", kg_factor=4)  # 1 Kg is 4 cones
		ensure_user(MANAGER, ["Sales User"])
		ensure_user(REP, ["Sales User"])
		ensure_user(OTHER_REP, ["Sales User"])
		make_sales_person(LEAD_PERSON, None, MANAGER, is_group=1)
		make_sales_person(REP_PERSON, LEAD_PERSON, REP)
		make_sales_person(OTHER_PERSON, None, OTHER_REP)
		user_sales_persons.clear_cache()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		user_sales_persons.clear_cache()

	def filters(self, **changes) -> DashboardFilters:
		values = {
			"from_date": str(get_first_day(self.today)),
			"to_date": str(get_last_day(self.today)),
			"granularity": "week",
			"territory": TERRITORY,
		}
		return DashboardFilters.build(**{**values, **changes})

	def deals(self, user="Administrator", **changes) -> dict:
		return DealMetrics(self.filters(**changes), SalesScope(user)).build()

	# ---- Kgs ----

	def test_lines_become_kgs_from_their_uom_or_item(self):
		converter = KgsConverter({KG_ITEM, PCS_ITEM, CONE_ITEM})

		self.assertEqual(converter.convert(10, "Kgs", None), 10)
		self.assertEqual(converter.convert(10, "kg", PCS_ITEM), 10)
		self.assertEqual(converter.convert(7, None, KG_ITEM), 7)  # no UOM: the item's stock UOM
		self.assertIsNone(converter.convert(50, "Pcs", PCS_ITEM))
		self.assertEqual(converter.convert(20, None, CONE_ITEM), 5)  # 20 cones at 4 a Kg

	# ---- 4. pipeline ----

	def test_the_pipeline_leaves_out_won_and_lost_deals_and_keeps_on_hold(self):
		make_deal("ZZT Requirement", REP, [(100, "Kgs", KG_ITEM), (40, "Pcs", PCS_ITEM)])
		make_deal("On Hold", OTHER_REP, [(30, None, KG_ITEM)])
		for status in ("Order Confirmed", "Dispatched", "Delivered"):
			make_deal(status, REP, [(1000, "Kgs", KG_ITEM)])
		make_deal("Lost", REP, [(1000, "Kgs", KG_ITEM)], lost_reason="ZZT Price")

		pipeline = self.deals()["pipeline"]

		self.assertEqual((pipeline["kgs"], pipeline["deals"], pipeline["not_in_kgs"]), (130, 2, 1))
		by_stage = {row["status"]: row["kgs"] for row in pipeline["by_stage"]}
		self.assertEqual((by_stage["ZZT Requirement"], by_stage["On Hold"]), (100, 30))
		self.assertNotIn("Delivered", by_stage)
		by_person = {row["sales_person"]: row["kgs"] for row in pipeline["by_sales_person"]}
		self.assertEqual(by_person, {REP_PERSON: 100, OTHER_PERSON: 30})

	def test_the_sales_person_filter_keeps_that_persons_deals(self):
		make_deal("ZZT Requirement", REP, [(100, "Kgs", KG_ITEM)])
		make_deal("ZZT Requirement", OTHER_REP, [(30, "Kgs", KG_ITEM)])
		# a stale Sales Person on the deal does not move it: the owner decides
		make_deal("ZZT Requirement", OTHER_REP, [(5, "Kgs", KG_ITEM)], custom_sales_person=REP_PERSON)

		self.assertEqual(self.deals(sales_persons=[REP_PERSON])["pipeline"]["kgs"], 100)
		self.assertEqual(self.deals(sales_persons=[LEAD_PERSON])["pipeline"]["kgs"], 100)  # a group: its team
		self.assertEqual(self.deals(sales_persons=[OTHER_PERSON])["pipeline"]["kgs"], 35)

	# ---- 5 and 6. delivered ----

	def test_a_deal_is_delivered_on_the_day_it_became_delivered(self):
		make_deal("Delivered", REP, [(200, "Kgs", KG_ITEM)])  # created as Delivered today
		moved = make_deal("ZZT Awaiting PO", REP, [(50, "Kgs", KG_ITEM)])
		moved.status = "Delivered"
		moved.save(ignore_permissions=True)
		make_deal("Order Confirmed", REP, [(999, "Kgs", KG_ITEM)])

		delivered = self.deals(granularity="day")["delivered"]

		today = next(row for row in delivered["trend"] if row["period"] == str(self.today))
		self.assertEqual((today["kgs"], today["deals"]), (250, 2))
		self.assertEqual(delivered["comparison"]["current"]["kgs"], 250)

	def test_delivered_kgs_compare_with_the_period_before_and_last_year(self):
		make_deal("Delivered", REP, [(150, "Kgs", KG_ITEM)])
		set_delivered_on(
			make_deal("Delivered", REP, [(100, "Kgs", KG_ITEM)]), add_days(get_first_day(self.today), -1)
		)
		set_delivered_on(make_deal("Delivered", REP, [(300, "Kgs", KG_ITEM)]), add_months(self.today, -12))

		comparison = self.deals()["delivered"]["comparison"]

		self.assertEqual(comparison["current"]["kgs"], 150)
		self.assertEqual(comparison["previous"]["kgs"], 100)
		self.assertEqual(comparison["last_year"]["kgs"], 300)
		self.assertEqual(comparison["vs_previous"], {"kg": 50, "pct": 50.0})
		self.assertEqual(comparison["vs_last_year"], {"kg": -150, "pct": -50.0})

	def test_a_change_from_nothing_has_no_percentage(self):
		self.assertEqual(_change(120, 0), {"kg": 120, "pct": None})

	# ---- 7. conversion ----

	def test_conversion_counts_how_far_each_deal_got(self):
		moved = make_deal("ZZT Requirement", REP, [])
		moved.status = "ZZT Quotation Sent"
		moved.save(ignore_permissions=True)
		make_deal("ZZT Requirement", REP, [])
		make_deal("Order Confirmed", REP, [])  # created late: counts as having passed the earlier stages
		make_deal("Lost", REP, [], lost_reason="ZZT Price")

		conversion = self.deals()["conversion"]

		reached = {row["stage"]: row["reached"] for row in conversion["stages"]}
		self.assertEqual(reached["ZZT Requirement"], 3)
		self.assertEqual(reached["ZZT Quotation Sent"], 2)
		self.assertEqual(reached["Order Confirmed"], 1)
		first = next(row for row in conversion["stages"] if row["stage"] == "ZZT Requirement")
		self.assertEqual(first["next_rate"], 66.7)
		self.assertEqual((conversion["won"], conversion["lost"], conversion["win_rate"]), (1, 1, 50.0))

	# ---- 1 to 3. customers ----

	def test_active_new_and_potential_customers(self):
		old = make_customer("ZZT Old Mills", REP_PERSON)
		new = make_customer("ZZT New Mills", REP_PERSON)
		make_customer("ZZT Lapsed Mills", REP_PERSON)
		make_order(old, 10, add_months(self.today, -14))
		make_order(old, 20, self.today)
		make_order(new, 30, self.today)
		make_order("ZZT Lapsed Mills", 40, add_months(self.today, -8))
		make_deal("ZZT Requirement", REP, [(60, "Kgs", KG_ITEM)], organization=make_org("ZZT Prospect"))
		ordering = make_org("ZZT Ordering Org", customer=old)
		make_deal("ZZT Requirement", REP, [(1, "Kgs", KG_ITEM)], organization=ordering)

		metrics = CustomerMetrics(self.filters(sales_persons=[REP_PERSON]), SalesScope())

		self.assertEqual(sorted(row["name"] for row in metrics.active()), sorted([old, new]))
		self.assertEqual([row["name"] for row in metrics.new()], [new])
		potential = metrics.potential()
		self.assertEqual(
			[(row["name"], row["kgs"], row["sales_person"]) for row in potential],
			[("ZZT Prospect", 60, REP_PERSON)],
		)

	# ---- 8. sales orders ----

	def test_sales_orders_from_deals_count_kgs_and_value(self):
		customer = make_customer("ZZT Order Mills", REP_PERSON)
		deal = make_deal("Order Confirmed", REP, [])
		make_order(customer, 25, self.today, deal=deal.name, rate=400)
		make_order(customer, 99, self.today)  # not from a deal

		orders = SalesOrderMetrics(self.filters(sales_persons=[REP_PERSON]), SalesScope()).build()

		self.assertEqual((orders["orders"], orders["kgs"], orders["value"]), (1, 25, 10000))
		self.assertEqual(orders["by_sales_person"][0]["sales_person"], REP_PERSON)

	# ---- scope ----

	def test_a_sales_person_sees_their_own_customers_and_a_head_sees_the_team(self):
		mine = make_customer("ZZT Mine", REP_PERSON)
		theirs = make_customer("ZZT Theirs", OTHER_PERSON)
		make_order(mine, 10, self.today)
		make_order(theirs, 10, self.today)

		frappe.set_user(REP)
		own = CustomerMetrics(self.filters(), SalesScope()).active()
		frappe.set_user(MANAGER)
		team = CustomerMetrics(self.filters(), SalesScope()).active()

		self.assertEqual({row["name"] for row in own} & {mine, theirs}, {mine})
		self.assertEqual(
			{row["name"] for row in team} & {mine, theirs}, {mine}
		)  # OTHER_PERSON is not below the head
		frappe.set_user(REP)
		self.assertEqual(SalesScope().sales_persons((OTHER_PERSON,)), ())

	def test_a_section_comes_through_the_api_and_its_cache(self):
		make_deal("ZZT Requirement", REP, [(100, "Kgs", KG_ITEM)])
		args = {
			"section": "deals",
			"from_date": str(get_first_day(self.today)),
			"to_date": str(get_last_day(self.today)),
			"sales_persons": f'["{REP_PERSON}"]',
			"territory": TERRITORY,
		}
		api._set_new_cache_version()  # Redis outlives the rollback of an earlier run

		self.assertEqual(api.get_section(**args)["pipeline"]["kgs"], 100)
		make_deal("ZZT Requirement", REP, [(5, "Kgs", KG_ITEM)])
		self.assertEqual(api.get_section(**args)["pipeline"]["kgs"], 100)  # still the cached one
		api._set_new_cache_version()  # what a deal's commit runs
		self.assertEqual(api.get_section(**args)["pipeline"]["kgs"], 105)

	def test_a_user_without_a_sales_role_is_refused(self):
		frappe.set_user("Guest")
		today = str(self.today)
		with self.assertRaises(frappe.PermissionError):
			api.get_section(section="deals", from_date=today, to_date=today)
		with self.assertRaises(frappe.PermissionError):
			api.get_rows(segment="pipeline", from_date=today, to_date=today)

	def test_wrong_input_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Granularity"):
			self.filters(granularity="hour")
		with self.assertRaisesRegex(frappe.ValidationError, "list of names"):
			self.filters(sales_persons='{"name": ["!=", ""]}')
		with self.assertRaisesRegex(frappe.ValidationError, "is not a list"):
			Rows(self.filters(), SalesScope(), "everything")

	def test_a_stage_list_holds_the_deals_of_that_stage(self):
		deal = make_deal("ZZT Quotation Sent", REP, [(12, "Kgs", KG_ITEM)])
		make_deal("ZZT Requirement", REP, [(5, "Kgs", KG_ITEM)])

		page = Rows(self.filters(), SalesScope(), "pipeline", "ZZT Quotation Sent").page()

		self.assertEqual([(row["name"], row["kgs"]) for row in page["rows"]], [(deal.name, 12)])


def make_deal(status: str, owner: str, lines: list[tuple], **fields):
	deal = frappe.get_doc(
		{
			"doctype": "CRM Deal",
			"status": status,
			"deal_owner": owner,
			"territory": TERRITORY,
			"products": [
				{
					"product_name": item or "line",
					"qty": qty,
					"rate": 1,
					"custom_uom": uom,
					"custom_item_code": item,
				}
				for qty, uom, item in lines
			],
			**fields,
		}
	)
	return deal.insert(ignore_permissions=True)


def set_delivered_on(deal, day):
	"""Move the day the deal became Delivered: its open status-log row."""
	row = deal.status_change_log[-1]
	frappe.db.set_value("CRM Status Change Log", row.name, "from_date", f"{getdate(day)} 10:00:00")
	frappe.db.set_value(
		"CRM Deal",
		deal.name,
		{"modified": f"{getdate(day)} 10:00:00", "creation": f"{getdate(day)} 10:00:00"},
		update_modified=False,
	)


def make_org(name: str, customer: str | None = None) -> str:
	ensure("CRM Organization", name, organization_name=name, custom_customer=customer)
	return name


def make_customer(name: str, sales_person: str) -> str:
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": CUSTOMER_GROUP,
				"territory": "All Territories",
				"sales_team": [{"sales_person": sales_person, "allocated_percentage": 100}],
			}
		).insert(ignore_permissions=True)
	return name


def make_order(customer: str, qty: float, day, deal: str | None = None, rate: float = 100):
	persons = frappe.get_all(
		"Sales Team", filters={"parent": customer, "parenttype": "Customer"}, pluck="sales_person"
	)
	order = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"company": COMPANY,
			"customer": customer,
			"transaction_date": getdate(day),
			"delivery_date": add_days(getdate(day), 7),
			"custom_crm_deal": deal,
			"items": [{"item_code": KG_ITEM, "qty": qty, "rate": rate}],
			"sales_team": [{"sales_person": person, "allocated_percentage": 100} for person in persons],
		}
	)
	order.flags.ignore_permissions = True
	order.insert()
	order.submit()
	return order


def make_item(code: str, uom: str, kg_factor: float | None = None):
	if frappe.db.exists("Item", code):
		return
	uoms = [{"uom": uom, "conversion_factor": 1}]
	if kg_factor:
		uoms.append({"uom": "Kg", "conversion_factor": kg_factor})
	item = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_group": "All Item Groups",
			"stock_uom": uom,
			"is_stock_item": 0,
			"uoms": uoms,
		}
	)
	if item.meta.has_field("gst_hsn_code"):
		# India Compliance asks every item for an HSN code
		item.gst_hsn_code = frappe.db.get_value("GST HSN Code", {}, "name")
	item.insert(ignore_permissions=True)


def make_sales_person(name: str, parent: str | None, user: str, is_group: int = 0):
	if frappe.db.exists("Sales Person", name):
		return
	employee = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": name,
			"gender": "Male",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"status": "Active",
			"company": COMPANY,
			"user_id": user,
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "Sales Person",
			"sales_person_name": name,
			"parent_sales_person": parent or "Sales Team",
			"is_group": is_group,
			"enabled": 1,
			"employee": employee.name,
		}
	).insert(ignore_permissions=True)


def ensure_user(email: str, roles: list[str]):
	if frappe.db.exists("User", email):
		return
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
	)
	user.insert(ignore_permissions=True)
	user.add_roles(*roles)


def ensure(doctype: str, name: str, **fields):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, **fields}).insert(ignore_permissions=True)
