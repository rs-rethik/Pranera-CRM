# Pranera CRM

A full-page, step-by-step **Convert to Deal** wizard for [Frappe CRM](https://github.com/frappe/crm),
installable as a PWA, that can also set up the matching **ERPNext Customer/Address/Contact** —
every ERPNext link field (Customer Group, Territory, GST Category, Payment Terms, Sales Person, …) is
chosen through a plain-language question rather than picked from a raw master record, using an
admin-configurable mapping (`Customer Wizard Mapping`), never hardcoded. It lives entirely in this app;
nothing under `apps/crm` is modified. Requires **erpnext** and **crm**.

* Route: `/deal_wizard/<lead>` (`?step=1..4`); `/deal_wizard/` lists open leads and local drafts.
* Steps: **1 Organization** (use existing / create new, + the ERPNext Customer/Address questions) →
  **2 Contact** (use existing / create new, + a Designation question) →
  **3 Deal details** (rendered from CRM's *Required Fields* layout for CRM Deal, never hardcoded) →
  **4 Review & confirm** (including a Question → Answer → Assigned value table for the Customer, with
  role-gated override).
* The actual conversion is done by CRM's own `convert_to_deal`; this app never reimplements it and
  never uses `ignore_permissions`. The ERPNext Customer step similarly never uses `ignore_permissions`
  and replaces CRM's own bare-bones, error-swallowing ERPNext bridge (see below) with an all-or-nothing
  one that reports errors clearly and never loses the Deal conversion.

**UI.** The look follows Frappe's own setup wizard: a centred card with progress dots above it, a centred
title, compact stock frappe-ui inputs and small *Back* / *Next* buttons inside the card. There is no custom
header, stepper, footer bar or theme; only frappe-ui components and its Tailwind tokens are used. The
"Pranera CRM" name lives in the page title, the PWA manifest and the app icon. Small conditional messages
(offline, draft restored, errors) appear inline in the card only when relevant.

Tested against Frappe 15.121 / Frappe CRM 1.84.

## Install

Requires **erpnext** installed on the site (`required_apps = ["crm", "erpnext"]`) and, for the GST questions,
**india_compliance**:

```bash
cd /home/rethik/frappe-bench-15
bench get-app india_compliance https://github.com/resilient-tech/india-compliance --branch version-15
bench get-app pranera_crm <repo-or-path>        # skip if the app is already in apps/
bench --site pranera.site install-app india_compliance
bench --site pranera.site install-app pranera_crm
bench build --app pranera_crm                   # links assets; the Vue build is committed (see below)
bench --site pranera.site migrate               # imports fixtures (Form Script, GST Category question seed), clears hook caches
bench restart                                    # or restart `bench start`
```

Match the `--branch` to your Frappe version. Without India Compliance the app still installs and works, but
the seeded GST questions (which target `Address.gst_category`/`gstin`) will fail their own validation —
disable or repoint them (see *ERPNext Customer* below).

Open a lead in CRM and press **Convert to Deal** (needs *Enable Convert to Deal Wizard* ticked, which is the default), or go to `/deal_wizard/<lead name>`.
The ERPNext Customer section additionally needs *ERPNext CRM Settings > Enabled* ticked (`/app/erpnext-crm-settings`, part of Frappe CRM — nothing this app adds).

> **HTTPS.** Service workers (and therefore installing the PWA) only work on `https://` or on
> `localhost`. Over plain `http://pranera.site:8002` the wizard works but is not installable.

> **Hook changes need a cache clear.** Frappe caches hooks in Redis; after changing `hooks.py` run
> `bench --site pranera.site clear-cache` (or `migrate`).

## Frontend

`frontend/` is a Vue 3 + frappe-ui + vue-router + Vite app (same stack and conventions as Frappe CRM's
own frontend).

```bash
cd apps/pranera_crm/frontend
yarn install
yarn build     # -> pranera_crm/public/frontend  and  pranera_crm/www/deal_wizard.html
yarn lint
yarn test      # vitest: validation, step guard, payload building
yarn dev       # Vite dev server on port 8082 (webserver_port 8002 + 80), proxying to the bench
```

* `yarn build` runs `vite build --base=/assets/pranera_crm/frontend/` and copies `index.html` to
  `www/deal_wizard.html`, exactly like CRM's `crm.html`. The `frappe-ui/vite` `jinjaBootData` plugin appends
  the Jinja block that injects `csrf_token` etc. as `window.*` globals (`www/deal_wizard.py` provides them).
* **The built output is committed** (unlike CRM, which builds it in CI) because `bench build` only builds
  the esbuild bundle, not Vite apps. Rebuild and commit after frontend changes.
* `yarn dev`: open `http://localhost:8082/deal_wizard/` . Dev has no Jinja, so boot data comes from
  `pranera_crm.www.deal_wizard.get_context_for_dev`, which requires
  `bench --site pranera.site set-config developer_mode 1`. Log in at `/login` (proxied) first.
  The service worker is disabled in dev.
* Icons: `frontend/scripts/generate_icons.py` regenerates `frontend/public/icons/*.png`.

## How it works

### Backend (`pranera_crm/api.py`)

| Method | Purpose |
| --- | --- |
| `get_wizard_context(lead)` | Read permission check; returns lead prefill data, candidate Organizations (name/website) and Contacts (email/phone/mobile), which of them CRM would silently reuse (`auto_organization`, `auto_contact`), the Deal quick-entry layout (`get_fields_layout("CRM Deal", "Required Fields")`), lead→deal defaults, deal statuses, `converted` / `lost` / `can_write`, and `customer` (the ERPNext Customer section context — see below). |
| `search_candidates(lead, …)` | Re-runs the matching for values the user edited. |
| `convert(lead, deal, existing_contact, existing_organization, lead_updates, setup_customer, customer_answers, contact_customer_answers, customer_address, customer_overrides, confirm_duplicate_customer)` | POST only. Checks write permission, locks the lead row, rejects already-converted (`LeadAlreadyConverted`) and Lost leads, validates existing records are readable, whitelists the deal payload to the quick-entry layout fields (never `lead`, `contacts`, `organization`, `owner`, …), checks required deal fields, applies `lead_updates`, then calls CRM's `convert_to_deal`. If `setup_customer` and the ERPNext bridge is on, also runs the Customer step (see below). Returns `{"deal": name, "customer": name \| None, "customer_error": message \| None, "duplicate_customer": name \| None}`. |
| `setup_customer_for_deal(deal, …)` | POST only. Runs (or retries) *just* the ERPNext Customer step for an already-converted deal — used after `convert` reports `duplicate_customer` or `customer_error`, so the Deal is never re-converted. Idempotent: if the deal already has a linked Customer, returns it without redoing anything. |
| `wizard_enabled()` | Is *Enable Convert to Deal Wizard* ticked? Used by the Lead page's Form Script. The other wizard APIs refuse with `WizardDisabled` when it is off. |
| `whoami()` | Guest-callable; lets the SPA tell an expired session from a genuine 403. |

`pranera_crm/erpnext_customer.py` additionally exposes `lookup_gstin(gstin)` (fetches a business name + address
from the GST public search via India Compliance, for the *Fetch* button) and `refresh_questions(scope, answers)`
(re-resolves a Dynamic question's live options as other answers change).

**Why `lead_updates`?** `convert_to_deal` builds a *new* Organization/Contact purely from the Lead's own
fields and accepts nothing else. So when the user chooses "Create new" and edits the values in steps 1-2,
`convert` first saves those edits onto the CRM Lead (permission-checked, same transaction) and then converts.
If the user picked an *existing* Organization/Contact, the corresponding edits are ignored.
Everything runs in one request/transaction: a failure rolls the lead edits and the `converted` flag back.

**CRM reuses matches silently.** With no existing record chosen, CRM still links an existing Contact that has
the lead's email/phone and an existing Organization with the same name. The wizard shows a banner
("CRM links that one instead of creating a duplicate") and pre-selects "Use existing" for exact matches.

### Serving

* `hooks.py` → `website_route_rules`: `/deal_wizard/<path:app_path>` → `deal_wizard` (www page).
* `www/deal_wizard.py`: guests are redirected (302) to `/login?redirect-to=<path+query>`; otherwise it provides
  `csrf_token`, `site_name`, `pranera_user`, `pranera_user_fullname`.

### Service worker scope (the trap, and the fix we chose)

A worker served from `/assets/pranera_crm/...` cannot control `/deal_wizard/` without a
`Service-Worker-Allowed` header. This bench runs `bench serve` with **no nginx**, so an nginx snippet would
not apply here. **We serve the worker from Frappe itself at `/deal_wizard/sw.js`:**

* `hooks.py` maps `/deal_wizard/sw.js` → endpoint `deal_wizard_sw` (a static rule wins over the `<path:>` catch-all)
  and registers `page_renderer = ["pranera_crm.sw.ServiceWorkerRenderer"]`.
* The renderer returns `public/frontend/sw.js` with `Service-Worker-Allowed: /deal_wizard/` and
  `Cache-Control: no-cache`. Served from `/deal_wizard/`, the default scope is already `/deal_wizard/`, so it works
  without any proxy configuration in development *and* production.
* `main.js` registers `/deal_wizard/sw.js` with `{ scope: '/deal_wizard/' }`.
* CRM's own worker lives under `/crm/`; the scopes are disjoint, and our caches use their own `pranera-crm`
  name prefix (caches are per-origin, not per-scope).

Alternative if you'd rather serve the worker from the asset path (nginx):

```nginx
location = /assets/pranera_crm/frontend/sw.js {
    add_header Service-Worker-Allowed "/deal_wizard/";
    add_header Cache-Control "no-cache";
}
```
and register `/assets/pranera_crm/frontend/sw.js` with `{ scope: '/deal_wizard/' }` in `frontend/src/main.js`.

### Caching / offline policy (`frontend/src/sw.js`)

* `/api/*`: **NetworkOnly**, all methods. Nothing is cached or replayed.
* Navigations under `/deal_wizard`: **NetworkFirst** (5 s timeout); redirects and non-200s are never stored.
* Precache: **hashed static assets only** (`assets/**` and icons). `index.html` is deliberately *not* precached: it
  embeds the session's CSRF token, and a stale one breaks every API call.
* The conversion request is **never queued offline** (replaying it could create duplicate contacts and
  organizations). Offline shows a banner and disables *Convert*; drafts are still saved locally.
* Session expiry: any 401/403/`CSRFTokenError` triggers a `whoami` check. Guest → `/login?redirect-to=…`.
  Live session with a stale token → a single automatic reload to pick up a fresh one.

### Drafts

Saved per user and lead in IndexedDB (localStorage fallback, plus a synchronous copy on page hide/unload),
debounced, restored on load ("Draft restored… Start over"), listed on `/deal_wizard/`, expired after 30 days
and cleared after a successful conversion.

## ERPNext Customer (question-driven, no raw pickers)

Converting a lead can also set up the matching ERPNext **Customer** (+ its **Address** and **Contact**),
appearing as an extra section in the Organization/Contact steps whenever *ERPNext CRM Settings > Enabled*
is on (the toggle CRM itself already ships — no new switch of ours). Every ERPNext link field is chosen
through a plain-language question; nothing is hardcoded.

### Why not just use CRM's own ERPNext bridge?

CRM ships `ERPNext CRM Settings` / `create_customer_from_deal`, which delegates to
`erpnext.crm.frappe_crm_api.create_customer`. That function only sets 7 fields (name, group, type,
territory, currency, industry, website — no GST, no Payment Terms, no Sales Person), and on **any**
failure it does `except Exception: frappe.log_error(...); pass` — silently discarding the error and
sometimes leaving a half-created Customer with no way for the user to know something went wrong. This app
replaces that path with its own (`pranera_crm/erpnext_customer.py`), reusing CRM's own `crm_deal` /
`erpnext_customer` cross-link fields so CRM's "View Customer" button and its lazy dedup on Sales Order
creation keep working unchanged — CRM's bridge itself is never modified or disabled.

### `Customer Wizard Mapping` — the question ↔ value config

A doctype (`/app/customer-wizard-mapping`), not a fixture-only concept — admins add, edit or disable
questions from the Desk like any other list. Each row is one question:

| Field | Meaning |
| --- | --- |
| `scope` | `Organization` or `Contact` — which wizard step it renders in. |
| `target_doctype` / `target_fieldname` | Which field the answer is written to (e.g. `Address.gst_category`). Checked against real doctype metadata on save; `Customer.sales_team` is special-cased (see below). |
| `question_type` | **Fixed**: a curated list of answers you define (child table `options`, each with a business-friendly `option_label` and the `mapped_value` actually written — leave `mapped_value` blank for an answer that only triggers a follow-up, see *overlay* below). **Dynamic**: a live, filtered list of records from another doctype (e.g. enabled Sales Persons) — still a picked list, never a raw search box. |
| `depends_on_question` / `depends_on_option` / `depends_on_operator` | Branching: this question only appears once the named question was answered a particular way. `Is` (default) matches one answer; `Is not` shows the question for every *other* answer (e.g. an Overseas category for every country except India). An unanswered parent hides the question either way. |
| `fallback_value` | Used, and flagged on the Review step, when the user's path leaves this field unanswered. |
| `is_mandatory` | The wizard blocks *Next*/submit until this question resolves something (an answer, a default, or a fallback) — used for the questions that must never be left blank. |
| `sequence` | Resolution/display order. Two questions targeting the *same* field combine by **overlay**: later ones win, but only when their chosen answer actually has a `mapped_value` — this is how "Regular or Composition?" and "Is it an SEZ unit?" (both writing `gst_category`) combine without a multi-answer combinator. |
| `override_roles` | Roles (one per line) allowed to override the resolved value on the Review step; everyone else sees a read-only result. |

Resolution (`pranera_crm/customer_wizard.py:resolve`) always runs **server-side** at submit time from the raw
answers — a tampered client payload can change which *answer* was picked, never what value that answer maps
to. The frontend (`frontend/src/lib/questions.js`) mirrors the same rules for instant UI feedback (visibility,
a live Review preview with the actual resolved values, grouped by Customer/Address/Contact) but is never
trusted.

**Shipped questions** (`pranera_crm/fixtures/customer_wizard_mapping.json`, freely editable): Customer Type,
Customer Group, Territory, Currency, Payment Terms (pre-answered from a seeded `100% Advance` template — see
`setup.py`), Address Type, GST Registered? → Regular/Composition → SEZ?, and Sales Person (Dynamic, filtered
to `enabled=1, is_group=0`; ships with no Sales Person records, so the question is skipped with nothing
assigned until you add some) for Organization; Designation for Contact. These use the real Customer
Group/Territory records already on a fresh ERPNext install — add finer ones (e.g. per-state Territories) and
point new answers at them with no code change.

### GST (via India Compliance)

Requires the `india_compliance` app (`bench get-app india_compliance --branch version-15`, matching this
bench's Frappe 15 — pick the branch matching yours). It adds `gstin` (Autocomplete) and `gst_category`
(Select, required) to Customer, and `gstin`/`gst_category`/`gst_state`/`gst_state_number` to Address, plus a
free-text `state` on Address that becomes an Autocomplete once India Compliance is in.

* **GST Category is written on Address**, not Customer (a business can be registered differently per
  location) — `erpnext_customer.py` mirrors the resolved value onto `Customer.gst_category` too, since core
  marks it required.
* **GSTIN**: validated via India Compliance's own `validate_gstin` (checksum) and `validate_gst_category`
  (e.g. a "Registered Regular" category needs an actual GSTIN) if the app is installed, else a regex format
  check as a fallback. A GSTIN already used by a *different* Customer's address is blocked as a likely
  duplicate entry (confirm through the *Duplicate customer* flow below if it's intentional).
* **"Fetch" button**: next to the GSTIN field, calls `lookup_gstin` (India Compliance's public GST search) and
  fills in the organization name and address fields that are still empty — never overwrites something you've
  already typed, and the server re-validates everything at submit regardless of where it came from.
* If India Compliance isn't installed, the GST question/fields simply don't exist on Address/Customer and any
  mapping row targeting `gst_category`/`gstin` fails its own `validate_target_field` check — remove or disable
  those seeded questions on a non-Indian deployment.

### All-or-nothing, without losing the Deal (two-phase, via savepoint)

The Customer/Address/Contact step runs in its own **savepoint**
(`frappe.db.savepoint()` / `rollback(save_point=...)`), taken right after the Deal conversion. A failure —
an invalid GST answer, a permission gap, anything — rolls back *only* the Customer/Address/Contact attempt;
the Deal conversion is already part of the same transaction and is untouched either way, so the user never
loses their conversion over a fixable data problem. The wizard shows the specific error with a **Try again**
button (re-submits just the Customer step via `setup_customer_for_deal`) and a **Continue to deal** escape
hatch. This is deliberately *not* one all-encompassing rollback: the original brief's "roll back everything"
was written for a standalone Customer-only wizard, and treating a secondary ERPNext hiccup as fatal to the
primary CRM action would be worse, not safer.

**Duplicate customer name**: an exact `customer_name` match raises for confirmation (`duplicate_customer` in
the response) rather than silently creating a second record or silently overwriting the existing one — the
wizard offers **Use existing customer**, which resubmits with `confirm_duplicate_customer=True` and *links*
the Deal to that Customer instead of creating a new one.

**Reuse, not duplication**: the Contact already created by the wizard's own Contact step gets a second
Dynamic Link row for the new Customer (not a duplicate Contact); the CRM Organization's existing `address`,
if any, is reused the same way and back-filled onto the Organization if it had none.

## Site properties (theme, language, formats)

The wizard follows the site the way CRM does:

| Property | How |
| --- | --- |
| **Theme** (light / dark / system) | Same mechanism as CRM: frappe-ui's `useTheme()`, stored in `localStorage["theme"]` and applied as `<html data-theme>`. Both apps share an origin, so the wizard uses whatever the user picked in CRM (default light, like CRM). Only theme-aware frappe-ui tokens are used (`surface-base`, `ink-*`, `outline-*`), and the saved theme is applied before first paint. |
| **Language** | The boot data carries `translated_messages` for the user's language (`frappe.translate.get_messages_for_boot`, merged from every app plus *Translation* records), exactly like CRM, and the UI uses a CRM-compatible `__()`. Wording reuses CRM's own strings where they exist ("Choose Existing", "Convert to Deal", "{0} is required", …), so those come pre-translated. `<html lang>` and `dir` follow the language, so right-to-left languages mirror. Field labels come from the doctype meta and are translated like CRM's. |
| **New strings** | `pranera_crm/locale/main.pot` lists the wizard's own strings (regenerate with `bench generate-pot-file --app pranera_crm`); add `<lang>.po` files or *Translation* records to translate them. Untranslated strings fall back to English. |
| **Date / time / number format, currency** | From *System Settings* (`date_format`, `time_format`, `number_format`, precisions) and *CRM Settings* (currency). Values on the Review step are shown in those formats, e.g. `₹ 12,34,567.50`, `21-09-2026`. |
| **Time zone** | System and user time zones are passed to frappe-ui (`systemTimezone` / `localTimezone`) as in CRM. |
| **Branding** | *CRM Settings > Branding*: the brand name becomes the tab title and the favicon is used, if set. |

Not followed: the installed PWA's name and icons come from a static manifest (a manifest can't vary per site),
and the date/time *pickers* use frappe-ui's own display.

## Turning the wizard on or off (CRM Settings)

A **Custom Field** on *CRM Settings* (`FCRM Settings`), **Enable Convert to Deal Wizard**
(`enable_convert_to_deal_wizard`, checkbox, shipped as a fixture), sits next to CRM's other "Enable …" options on
the *Settings* tab of `/app/fcrm-settings`. (CRM's own Settings modal renders a fixed set of fields, so the new
option lives on the Desk form.)

* **Ticked (default)**: *Convert to Deal* on a lead opens the wizard.
* **Unticked**: CRM's standard flow applies everywhere:
  * the Form Script does nothing, so CRM's own *Convert to Deal* button and dialog are shown;
  * `/deal_wizard/…` redirects to the same lead in CRM (`/deal_wizard/` to `/crm`);
  * the wizard's APIs refuse with `WizardDisabled`, and a wizard tab that is already open falls back to the lead
    page when you press *Convert* (nothing is converted).

The default is written once, on install/migrate, and remembered, so an admin's choice is never overwritten by a
later `migrate`. (Frappe stores an untouched checkbox as `0` once the settings are saved for any reason, so
"never set" cannot be told apart from "unticked" without that marker.)

## Entry point from the Lead page

`pranera_crm/fixtures/crm_form_script.json` installs a **CRM Form Script** ("Pranera Convert Wizard",
`dt = CRM Lead`, `view = Form`) that makes the Lead page's **Convert to Deal** open the wizard:

* It adds a **Convert to Deal** action (CRM's `setupForm({ doc })` → `{ actions: [...] }` contract) that
  navigates to `/deal_wizard/<lead>`. It is omitted once the lead is converted.
* CRM's own **Convert to Deal** button is **hidden** (only while the switch above is on). A Form Script has no API to remove built-in buttons, so the
  script hides it in the DOM (a `MutationObserver` on `div.inline-flex > button` whose label is
  `Convert` / `Convert to Deal`; CRM wraps only that button in a Tooltip `div.inline-flex`). Nothing in
  `apps/crm` is modified.
* On phones CRM folds custom actions into the "⋯" menu, so **Convert to Deal** lives there.
* The action uses CRM's default custom-action button style (a Form Script cannot restyle it).

The script is not marked *Standard*, so admins can edit or disable it (disabling it and reloading restores CRM's
button). The fixture is re-synced on every `migrate`. Because the hiding relies on CRM's current markup, re-check
it after CRM upgrades. If it ever stops matching, the stock button simply reappears (nothing breaks).

The bulk *Convert to Deal* on the Leads list is not affected.

### Sturdier alternative: patch CRM's own button

If you prefer to change CRM's source instead of hiding a DOM node (this is **not** applied here, and **must be
re-applied after every CRM upgrade**), make this one-line change in both `apps/crm/frontend/src/pages/Lead.vue`
(≈ line 321) and `apps/crm/frontend/src/pages/MobileLead.vue` (≈ line 391):

```diff
-const showConvertToDealModal = ref(false)
+const showConvertToDealModal = computed({ get: () => false, set: () => window.location.assign(`/deal_wizard/${encodeURIComponent(props.leadId)}`) })
```

The template's `@click="showConvertToDealModal = true"` then navigates to the wizard and the modal never renders;
rebuild CRM's frontend afterwards (`cd apps/crm/frontend && yarn build`). If you do this, disable the
"Pranera Convert Wizard" Form Script so there aren't two buttons.

## Tests

```bash
cd /home/rethik/frappe-bench-15
# `allow_tests` must be enabled on the site, or set CI=1 for a one-off run:
CI=1 bench --site pranera.site run-tests --app pranera_crm --skip-before-tests --skip-test-records
cd apps/pranera_crm/frontend && yarn test && yarn lint
```

Python tests, all rolled back automatically at the end of each test:

* `test_api.py` — permission denied, already converted (flag and deal), new org + new contact (with
  `lead_updates`), existing org + existing contact (edits ignored, nothing duplicated), Lost leads, deal
  payload whitelisting, missing required deal fields, unknown existing records, context
  permissions/candidates, and `whoami`.
* `test_customer_wizard.py` — the resolution engine directly: fixed/single-option auto-answer, fallback,
  branching (`Is` / `Is not`, hidden grandchildren), the sequential overlay, Dynamic options + filter
  interpolation, the `sales_team` special case, role-gated override, `is_mandatory` blocking, and every
  `Customer Wizard Mapping.validate()` rule (unknown target field, table targets, duplicate/missing options,
  bad Dynamic source, branching cycles/cross-scope, unknown override roles). Tests that call `resolve()`
  first disable the seeded fixture questions (`isolate_from_seed_questions`) so they only see their own
  ad-hoc ones.
* `test_erpnext_customer.py` — end to end through `convert()`/`setup_customer_for_deal()`: full setup creates
  a correctly-linked Customer/Address/Contact, GST validation failure leaves the Deal intact and retryable,
  role-gated override, the disabled-bridge no-op, duplicate-name confirm-and-link and a duplicate-GSTIN block
  (without touching the original Deal either way), reusing an Organization's existing Address / a Deal's
  existing Contact (no duplicates), Sales Team row creation, permission denial, `lookup_gstin` (mocking India
  Compliance's API), the retry endpoint's idempotency once a Customer is already linked, and a regression test
  that `get_wizard_context` sends *every* question up front (not just the ones visible with no answers yet —
  a follow-up question must still be there for the client to reveal later).

Frontend (`frontend/tests/`): `wizard-logic.test.js` / `site-properties.test.js` (existing Deal Wizard
behaviour) plus `questions.test.js` for `lib/questions.js` — the same branching/overlay/fallback/mandatory
rules mirrored client-side, plus `resolvedFields`'s grouped, overlay-aware value computation for the Review
step.

## Manual verification checklist

1. **Desktop, end to end.** Open an unconverted lead → *Convert to Deal* (CRM's own button is hidden; on a phone it is in the ⋯ menu). Step through the four steps (dots at the top show progress), use *Back*, the
   browser back button and a page reload (step and values must survive). Press *Convert to Deal*; you land on
   `/crm/deals/<name>` and the lead shows as converted. Re-open `/deal_wizard/<lead>`: it says the lead is
   already converted and links to the deal.
2. **PWA on a phone-sized viewport.** Chrome DevTools → toggle device toolbar (e.g. 390×844) → open `http://localhost:8002/deal_wizard/`
   (or your HTTPS URL). *Application → Manifest*: no errors, name "Pranera CRM", scope/start URL `/deal_wizard/`,
   192/512 + maskable icons. *Application → Service Workers*: `/deal_wizard/sw.js` **activated**, scope
   `…/deal_wizard/`. The install icon appears in the address bar (Installability panel lists no blockers).
   Install it and confirm it opens standalone.
3. **Expired session.** With the wizard open on step 4, delete the `sid` cookie (or log out in another tab) and press
   *Convert*. You must be redirected to `/login?redirect-to=/deal_wizard/<lead>?step=4`, with **no CSRF error**.
   After logging in you return to the wizard and the draft is restored.
4. **Offline.** DevTools → Network → Offline: the banner appears and *Convert* is disabled; go back online and it re-enables.
5. **Service worker hygiene.** *Application → Cache Storage* shows `pranera-crm-*` caches only; `index.html` and `/api/*` are
   never in them. CRM at `/crm` still works and keeps its own worker.
6. **ERPNext Customer, happy path.** With *ERPNext CRM Settings* enabled, convert a lead answering the GST
   question chain ("Yes" → "Regular" → SEZ "No"), fill the Address (Country India needs a real `State`), and
   submit. On the resulting Customer: `customer_type`/`customer_group`/`territory`/`default_currency`/
   `payment_terms`/`gst_category` are set; its `customer_primary_address`/`customer_primary_contact` point at
   an Address/Contact that also carry a `Customer` Dynamic Link row (check *Address → Links*); `crm_deal` on
   the Customer and `erpnext_customer` on the CRM Deal cross-reference each other, and CRM's own **View
   Customer** button (on the Deal) resolves to it.
7. **GSTIN fetch and validation.** Type a GSTIN and press *Fetch* — organization name and address fields
   populate (needs real internet access to the GST public API; a bad/unreachable lookup shows a clear inline
   error, not a crash). Answer "GST Registered? Yes → Regular" but leave GSTIN blank and submit: the Deal
   still converts, and you land on a "Try again" panel with India Compliance's own validation message.
8. **Deal survives a Customer-step failure.** Reproduce #7's error, then check the CRM Deal directly — it
   exists and is not rolled back, only the Customer/Address/Contact attempt is. Press **Try again** with a
   valid GSTIN (or **Continue to deal** to skip it) and confirm no duplicate Customer/Address/Contact is left
   behind either way.
9. **Duplicate customer name.** Pre-create a Customer with the same name the wizard would use, then convert;
   you land on **Use existing customer**, and afterwards the Deal is linked to that pre-existing Customer, not
   a second one.
10. **ERPNext CRM Settings disabled.** Untick *Enabled* and convert a lead: no Customer section appears, the
    Deal converts exactly as before this feature existed, and `/deal_wizard/…` with the bridge off elsewhere
    still behaves normally.

## Known limitations

* UI strings are English only (no translation layer yet).
* `depends_on` / `mandatory_depends_on` on Deal fields are not evaluated client-side (conditional required fields
  are left to the server's validation); field types the wizard can't render (Attach, Table, HTML, …) are shown
  as "add it on the deal after converting".
* If a "Create new" contact/organization would match an existing record, CRM links the existing one (see above);
  the wizard warns but cannot change that CRM behaviour.
* Editing values in "Create new" modifies the CRM Lead (that is how CRM builds the new records).
* One Customer, one Address, one Contact per conversion — no add/remove-multiple UI (a deliberate "Light"
  scope: a Lead already has one organization and one primary contact).
* A Dynamic question's live options are resolved once, from the answers known at page load; if you configure
  one whose `source_filters` reference another question (e.g. suggest Sales Person by Territory), its option
  list won't refresh automatically as that other question is answered — `refresh_questions` exists for this
  and just isn't wired into the frontend yet, since no seeded question currently needs it.
* Country is a plain searchable Link (like the existing Organization/Contact search), not a mapping question —
  its ~250 entries are already the business terms, unlike Customer Group/GST Category where the right internal
  value isn't obvious from the label alone.
