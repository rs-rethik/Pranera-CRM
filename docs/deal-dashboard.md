# Deal Dashboard

The Deal Dashboard shows customers, deal quantities in kilograms, deliveries, stage conversion and Sales Orders made from deals. It opens inside Frappe CRM and is part of `pranera_crm`. The `crm` app is not changed.

## Open the dashboard

1. Open Frappe CRM (`/crm`).
2. Select **Deal Dashboard** in the sidebar, below **Call Logs**.

The dashboard opens in a panel over the CRM page. Press `Esc` or select a CRM page to close it. The address bar keeps the filters (`?pranera_panel=dashboard&pranera_q=...`), so you can copy the link to share the same view.

Every user with the Sales User or Sales Manager role can open it.

## Filters

| Filter | Effect |
|---|---|
| Period | Today, This week (Monday to Sunday), This month, This year or a custom range. |
| Daily / Weekly / Monthly / Yearly | How the trend charts group the period. The period sets a default; you can change it. |
| Sales Person | One or more Sales Persons. A group in the Sales Person tree includes everyone below it. |
| Territory | A CRM Territory and its child territories. It applies to deal widgets and to potential customers only. Customers and Sales Orders use ERPNext's Territory tree, which is a different tree. |

## Who sees what

- **Deals** are read with `frappe.get_list`, so CRM's own rule applies. A Sales User sees the deals they own or are assigned to. A Sales Manager or System Manager sees all deals. If the sales hierarchy is turned on in FCRM Settings, a manager in the hierarchy also sees the deals of their team.
- **Customers and Sales Orders**: a Sales Manager or System Manager sees all of them. Another user sees the customers and orders of their own Sales Person and of the Sales Persons below it in the Sales Person tree.
- A user's Sales Person comes from Sales Person → Employee → User.
- A user who is not linked to a Sales Person sees no customer or order numbers. The page says so.

## How each number is calculated

### Sales Person of a record

| Record | Sales Person |
|---|---|
| Deal | The Sales Person of the deal owner. If the owner is not linked to one, the deal's Sales Person field. |
| Customer | The first row of the customer's Sales Team. |
| Sales Order | The first row of the order's Sales Team. |
| Potential customer (CRM Organization) | The Sales Person of its most recent open deal. |

### Kilograms

A deal product line is in kilograms when its UOM is Kgs, Kg or kg. When the line has no UOM, the stock UOM of its item decides. A line in another UOM is converted only through the item's UOM Conversion Detail to Kg. Lines that cannot be converted, for example Pcs, are left out and counted as "not in Kg".

Sales Order rows use their stock quantity and stock UOM, with the same rules.

### Customers

| Number | Calculation |
|---|---|
| Active customers | Customers with a submitted Sales Order dated in the 180 days up to the end of the period. |
| Newly acquired | Customers whose first ever submitted Sales Order is dated inside the period. |
| Potential customers | CRM Organizations with an open deal (stage type Open, Ongoing or On Hold) whose Customer has no submitted Sales Order. The Customer is the organization's Customer field, or the Customer field of its deals. |

The customer list shows the last order date (or last deal date for potential customers) and the Kgs ordered in the same window (or the Kgs of the open deals).

Active customers are counted from Sales Orders, not Sales Invoices, because the Sales User role cannot read Sales Invoices in ERPNext.

### Deals

| Number | Calculation |
|---|---|
| Pipeline | Kgs and count of the deals whose stage type is not Won or Lost: today this is every stage except Order Confirmed, Dispatched, Delivered and Lost. On Hold is included. It shows the pipeline as it is now; the period does not apply. |
| Delivered | Kgs of the deals in the Delivered stage, by the day they became Delivered. The day is when the deal's current Delivered status began in its status log. A deal created as Delivered became Delivered on its creation day. |
| Comparison | Delivered Kgs of this period, of the period of the same length just before it, and of the same dates last year, with the change in Kg and %. There is no % when the earlier period has no deliveries. |
| Conversion by stage | Deals created in the period. For each stage of the path (Open, Ongoing and Won stages in position order, without On Hold and Lost), the number of deals that got that far: the furthest stage in the deal's status log or its current stage. A deal created at a later stage counts as having passed the earlier ones. "Move on" is the share of those deals that got to the next stage. |
| Win rate | Deals created in the period: won (Order Confirmed, Dispatched or Delivered) ÷ (won + Lost). |

### Sales Orders from deals

Submitted Sales Orders dated in the period that came from a deal: the order's CRM Deal field is set, or the order was made from a Quotation that CRM made from a deal (`Quotation.crm_deal`). The dashboard shows their count, Kgs (stock quantity of rows in kilograms) and value (net total in company currency), by period and by Sales Person.

## Drill-down

Select a card, a bar or a number in a table to see the records behind it. Sort the list by any column. A deal or organization opens in CRM; a customer or Sales Order opens in Desk in a new tab.

## Cache

Each section is cached for 60 seconds per user and set of filters. The cache key changes when a CRM Deal, CRM Organization or Customer is saved, or a Sales Order is submitted, cancelled or updated after submit.

## Fields the dashboard reads

These custom fields were made on Pranera's site. `pranera_crm` ships the same definitions as fixtures, without a module, so uninstalling the app does not remove them: `CRM Products.custom_uom`, `CRM Products.custom_item_code`, `CRM Organization.custom_customer`, `CRM Organization.custom_sales_person`, `CRM Deal.custom_customer`, `CRM Deal.custom_sales_person`, `Sales Order.custom_crm_deal`.

## Add a widget

1. Add a method to the section class in `pranera_crm/deal_dashboard/` (`customers.py`, `deals.py` or `sales_orders.py`) and add its result to `build()`. Read deals through `DealQuery.get_list` so the filters and permissions apply.
   - `frappe.get_list` does not accept `CASE`, `COALESCE`, `DATE_FORMAT` or `MAX()` on a joined table's column. Group by plain fields and combine the rows in Python.
2. For a drill-down list, add a segment to `rows.py`.
3. Add a `ChartCard` to `frontend/src/pages/DealDashboard.vue`, with chart options in `frontend/src/lib/dashboardCharts.js`.
4. Add a test to `pranera_crm/tests/test_deal_dashboard.py`, then run `yarn build` in `frontend/`.

## Limits

- The sidebar item depends on the markup of CRM's sidebar (`MARKUP` in `crm_sidebar_ext.js`). If a CRM update changes it, the item does not show; open `/deal_wizard/dashboard` directly until the selectors are fixed.
- A team head with only the Sales User role sees team customers and orders, but only their own deals, until CRM's sales hierarchy is turned on or they get the Sales Manager role.
- Measured on the development site with 60,000 Sales Orders, 15,000 customers and 5,000 deals: the slowest section (Customers, a full year) took 1.4 seconds without the cache; the three sections load at the same time.
