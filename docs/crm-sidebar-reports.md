# Reports in the CRM sidebar

**Status:** implemented (2026-10-07). It is a port of [frappe/crm PR #2912](https://github.com/frappe/crm/pull/2912)
(closed upstream as "not planned"), kept entirely in `pranera_crm`. The `crm` app is not modified.

## What the user gets

- A **Reports** section at the bottom of CRM's sidebar, with one item per report the user pinned.
  Clicking an item opens the report in a panel over CRM's content area; the sidebar stays visible.
- Clicking the **Reports** label opens the page where reports are added and removed ("Add Existing
  Report" dialog). PR #2912 put this under Settings > Reports; CRM's Settings modal is hardcoded in
  core, so it lives in the panel instead.
- A report page with filters (Link, Dynamic Link, Select, MultiSelect, Date, date range, Check,
  text/number), a table with a total row, record links into CRM, Print (browser / PDF) and Export
  (Excel / CSV).
- Which reports are offered: Query / Script / Custom Reports with **module = FCRM**, not disabled,
  not prepared, and runnable by the user (roles, Custom Role, report permission on the ref doctype).
  Pins are stored per user in `tabDefaultValue` (`_crm_pinned_reports`, same key as the PR).

## Pieces

| File (in `apps/pranera_crm`) | Role |
|---|---|
| `pranera_crm/report.py` | API: `get_fcrm_reports`, `get_pinned_reports`, `pin_report(s)`, `unpin_report`, `get_report_meta`, `get_report_data`, `export_report`. Port of the PR's `crm/api/report.py`; `export_report` also works on Frappe v15 (no cell styles, no `decimal_sep`) |
| `pranera_crm/www/crm.py`, `crm.html` | Take over `/crm` (installed after `crm`), include CRM's own page and add one script tag |
| `pranera_crm/public/js/crm_sidebar_ext.js` | Builds the sidebar section from CRM's rendered markup, opens the panel (iframe), closes it on navigation / Esc. Messages from the page: `pranera:close-panel`, `pranera:pins-changed`, `pranera:open-crm` |
| `pranera_crm/www/deal_wizard.py` | `is_reports_request()`: `/deal_wizard/reports...` stays reachable when the wizard is switched off |
| `frontend/src/pages/Reports.vue`, `Report.vue` | Pinned list + add dialog; the report page |
| `frontend/src/components/Report{Export,Print}Modal.vue`, `MultiLinkSelect.vue` | Ported from the PR |
| `frontend/src/lib/reports.js` | Ported from the PR's `utils/reports.js` (filters, values, print HTML, downloads) |
| `frontend/src/router.js` | `/reports` and `/reports/:reportName`, before `/:name` (the wizard) |
| `pranera_crm/tests/test_report.py`, `frontend/tests/reports.test.js` | Ported tests |

## Why it's done this way

- CRM's sidebar is hardcoded (`crm/frontend/src/components/Layouts/AppSidebar.vue`) and has no hook
  for extra items.
- Frappe resolves www pages by searching installed apps in reverse install order, and `pranera_crm`
  requires `crm`, so `pranera_crm/www/crm.html` takes over `/crm`. It `include`s `crm/www/crm.html`
  instead of copying it, so CRM's hashed assets and boot script stay in sync after every update.
- The script clones CRM's "Call Logs" sidebar item, so the new items get CRM's exact styling.

## Known limitations

- **Fragile selectors:** the script relies on CRM's rendered markup (`[data-slot="sidebar"]`,
  `[data-slot="sidebar-item"]`, `a[href^="/crm/call-logs"]`, `.overflow-y-auto`, frappe-ui's
  active/inactive classes). They are all in the `MARKUP` constant. If an update changes them the
  section silently disappears and CRM keeps working.
- **Stale script after edits:** `?v=` is `get_build_version()` and only changes on `bench build`.
  Run `bench build --app pranera_crm` after editing the JS.
- **No deep links:** the panel doesn't change CRM's URL. A report can be opened directly at
  `/deal_wizard/reports/<name>`.
- **Desk filter scripts** run in the browser with desk APIs stubbed (as in the PR); a script that
  fails shows a warning and no filters.
- **Better long-term option:** if upstream CRM accepts a sidebar extension hook, switch to it and drop
  the `/crm` page override.

## Rebuilding

`cd frontend && yarn build`, then `bench build --app pranera_crm` and `bench --site <site> clear-cache`.
Check: open `/crm`, View Source. It should be CRM's page plus one `crm_sidebar_ext.js` script tag.

## Earlier prototype (parked 2026-09-23)

A first version with a single "Reports" item and a placeholder deal-count report was built and then
removed. This implementation replaces it (same override and panel mechanism).
