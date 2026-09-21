# Pranera CRM

A full-page, step-by-step **Convert to Deal** wizard for [Frappe CRM](https://github.com/frappe/crm),
installable as a PWA. It lives entirely in this app; nothing under `apps/crm` is modified.

* Route: `/deal_wizard/<lead>` (`?step=1..4`); `/deal_wizard/` lists open leads and local drafts.
* Steps: **1 Organization** (use existing / create new) → **2 Contact** (use existing / create new) →
  **3 Deal details** (rendered from CRM's *Required Fields* layout for CRM Deal, never hardcoded) →
  **4 Review & confirm**.
* The actual conversion is done by CRM's own `convert_to_deal`; this app never reimplements it and
  never uses `ignore_permissions`.

**UI.** The look follows Frappe's own setup wizard: a centred card with progress dots above it, a centred
title, compact stock frappe-ui inputs and small *Back* / *Next* buttons inside the card. There is no custom
header, stepper, footer bar or theme; only frappe-ui components and its Tailwind tokens are used. The
"Pranera CRM" name lives in the page title, the PWA manifest and the app icon. Small conditional messages
(offline, draft restored, errors) appear inline in the card only when relevant.

Tested against Frappe 15.121 / Frappe CRM 1.84.

## Install

```bash
cd /home/rethik/frappe-bench-15
bench get-app pranera_crm <repo-or-path>        # skip if the app is already in apps/
bench --site pranera.site install-app pranera_crm
bench build --app pranera_crm                   # links assets; the Vue build is committed (see below)
bench --site pranera.site migrate               # imports the Form Script fixture, clears hook caches
bench restart                                    # or restart `bench start`
```

Open a lead in CRM and use **Convert (Wizard)**, or go to `/deal_wizard/<lead name>`.

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
| `get_wizard_context(lead)` | Read permission check; returns lead prefill data, candidate Organizations (name/website) and Contacts (email/phone/mobile), which of them CRM would silently reuse (`auto_organization`, `auto_contact`), the Deal quick-entry layout (`get_fields_layout("CRM Deal", "Required Fields")`), lead→deal defaults, deal statuses, and `converted` / `lost` / `can_write`. |
| `search_candidates(lead, …)` | Re-runs the matching for values the user edited. |
| `convert(lead, deal, existing_contact, existing_organization, lead_updates)` | POST only. Checks write permission, locks the lead row, rejects already-converted (`LeadAlreadyConverted`) and Lost leads, validates existing records are readable, whitelists the deal payload to the quick-entry layout fields (never `lead`, `contacts`, `organization`, `owner`, …), checks required deal fields, applies `lead_updates`, then calls CRM's `convert_to_deal`. Returns the new deal name. |
| `whoami()` | Guest-callable; lets the SPA tell an expired session from a genuine 403. |

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

## Entry point from the Lead page

`pranera_crm/fixtures/crm_form_script.json` installs a **CRM Form Script** ("Pranera Convert Wizard",
`dt = CRM Lead`, `view = Form`) that adds a **Convert (Wizard)** action to the Lead page using CRM's
`setupForm({ doc })` → `{ actions: [...] }` contract (hidden once the lead is converted). It is not marked
*Standard*, so admins can edit or disable it. Note the fixture is re-synced on every `migrate`.

Form Scripts cannot hide CRM's stock **Convert to Deal** button, and we do not patch `apps/crm`. If you want
the stock button to open the wizard instead, apply this optional one-line change **in both files** (it is
*not* applied here, and **must be re-applied after every CRM upgrade**):

`apps/crm/frontend/src/pages/Lead.vue` (≈ line 321) and `apps/crm/frontend/src/pages/MobileLead.vue` (≈ line 391):

```diff
-const showConvertToDealModal = ref(false)
+const showConvertToDealModal = computed({ get: () => false, set: () => window.location.assign(`/deal_wizard/${encodeURIComponent(props.leadId)}`) })
```

The template's `@click="showConvertToDealModal = true"` then navigates to the wizard and the modal never
renders. Rebuild CRM's frontend afterwards (`cd apps/crm/frontend && yarn build`). Bulk convert from the Leads
list is not affected.

## Tests

```bash
cd /home/rethik/frappe-bench-15
# `allow_tests` must be enabled on the site, or set CI=1 for a one-off run:
CI=1 bench --site pranera.site run-tests --app pranera_crm --skip-before-tests --skip-test-records
cd apps/pranera_crm/frontend && yarn test && yarn lint
```

Python tests (`pranera_crm/tests/test_api.py`) cover: permission denied, already converted (flag and deal),
new org + new contact (with `lead_updates`), existing org + existing contact (edits ignored, nothing
duplicated), Lost leads, deal payload whitelisting, missing required deal fields, unknown existing records,
context permissions/candidates, and `whoami`. They run inside the test transaction and roll back.

## Manual verification checklist

1. **Desktop, end to end.** Open an unconverted lead → *Convert (Wizard)*. Step through the four steps (dots at the top show progress), use *Back*, the
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

## Known limitations

* UI strings are English only (no translation layer yet).
* `depends_on` / `mandatory_depends_on` on Deal fields are not evaluated client-side (conditional required fields
  are left to the server's validation); field types the wizard can't render (Attach, Table, HTML, …) are shown
  as "add it on the deal after converting".
* If a "Create new" contact/organization would match an existing record, CRM links the existing one (see above);
  the wizard warns but cannot change that CRM behaviour.
* Editing values in "Create new" modifies the CRM Lead (that is how CRM builds the new records).
