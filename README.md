<div align="center">

<h1>Pranera CRM</h1>

**A step-by-step "Convert to Deal" wizard for Frappe CRM, with guided ERPNext Customer creation**

</div>

## Pranera CRM

Pranera CRM replaces Frappe CRM's *Convert to Deal* dialog with a full-page wizard (installable as a PWA)
that converts a Lead into a Deal and, in the same flow, creates the matching ERPNext **Customer**, **Address**
and **Contact**. Instead of raw record pickers, every ERPNext link field (Customer Group, Territory, GST
Category, Payment Terms, …) is chosen through a plain-language question that an admin configures.

The conversion itself is done by CRM's own `convert_to_deal`. Nothing under `apps/crm` is modified.

### Key Features

-   **Four-step wizard:** Organization → Contact → Deal details → Review, at `/deal_wizard/<lead>`. Deal
    fields are rendered from CRM's own *Required Fields* layout.
-   **Question-driven Customer setup:** admins define questions and answers in **Customer Wizard Mapping**;
    each answer maps to a real field value, so users never see raw ERPNext masters.
-   **GST first:** "Does the customer have a GST Number?" fetches the business name and address through India
    Compliance and locks those fields; otherwise they are entered by hand.
-   **Individual or Business:** an Individual never gets a CRM Organization; the Customer is named after the
    contact.
-   **Reuse existing records:** choose an existing Organization, Contact or Address from a list of likely
    matches instead of creating duplicates.
-   **Email verification:** a new contact's email must be verified with a one-time code before submit.
-   **Deal is never lost:** the Customer step runs in a savepoint; if it fails, the Deal stays converted and
    the user can fix the answers and retry.
-   **Safe by default:** new Customers are created *disabled*, the Sales Person comes from the logged-in user,
    and CRM's own competing "create Customer on status change" setting is switched off.
-   **Drafts and offline:** progress is saved per lead on the device and restored on return.

### Requirements

-   Frappe 15, [Frappe CRM](https://github.com/frappe/crm) and ERPNext
-   [India Compliance](https://github.com/resilient-tech/india-compliance) for the GST questions
-   A default outgoing **Email Account** for email verification

Tested against Frappe 15.121 and Frappe CRM 1.84.

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app india_compliance https://github.com/resilient-tech/india-compliance --branch version-15
bench get-app https://github.com/rs-rethik/Pranera-CRM --branch develop
bench --site your.site install-app india_compliance
bench --site your.site install-app pranera_crm
bench --site your.site migrate
bench restart
```

The Vue build is committed, so no frontend build is needed to run the app.

## Usage

Open a Lead in CRM and click **Convert to Deal**, or go to `/deal_wizard/<lead name>`.

## Configuration

| Where | What |
| --- | --- |
| **Desk → FCRM Settings** (`/app/fcrm-settings`), *Defaults* tab → **Enable Convert to Deal Wizard** | On by default. Off falls back to CRM's standard dialog. It is not in the CRM app's own Settings popup, which has a fixed list of switches and no extension point. |
| **Desk → ERPNext CRM Settings** (`/app/erpnext-crm-settings`, or CRM Settings → ERPNext) → **Enabled** | Turns on the ERPNext Customer section of the wizard. |
| **Customer Wizard Mapping** | The questions, answers and the field values they set. Editable by System Manager only; edits survive `bench migrate`. |
| **Email Account** | A default outgoing account, needed to send verification codes. |

In the form, the target doctype is limited to Customer, Address, Contact and CRM Lead, the target fieldname is picked from that doctype's fields, and override roles are a multiselect.

A Customer Wizard Mapping row defines a question, its answers (each with the value it writes), the target
field, optional branching (`depends_on_question`), an optional secondary target, mandatory/fallback rules, and
which roles may override the result on the Review step. Fixed questions list curated answers; Dynamic
questions list live records from another doctype. Mapped Link and Select values are validated when saved.

## Development

```bash
cd apps/pranera_crm/frontend
yarn install
yarn dev        # Vite dev server on :8082 (needs developer_mode on the site)
yarn build      # builds into pranera_crm/public/frontend and www/deal_wizard.html
yarn lint && yarn test
```

Rebuild and commit the output after frontend changes.

```bash
bench --site your.site run-tests --app pranera_crm
```

This app uses `pre-commit` for formatting and linting (ruff, prettier, eslint):

```bash
cd apps/pranera_crm
pre-commit install
```

### Layout

-   `pranera_crm/api.py`: wizard context, candidate search, `convert`, `setup_customer_for_deal`
-   `pranera_crm/customer_wizard.py`: question resolution engine
-   `pranera_crm/erpnext_customer.py`: Customer, Address and Contact creation; GSTIN lookup
-   `pranera_crm/email_verification.py`: email one-time codes
-   `pranera_crm/setup.py`, `pranera_crm/data/`: install and migrate seeding
-   `frontend/`: Vue 3 + frappe-ui + Vite app

## Known Limitations

-   UI strings are English only.
-   One Customer, one Address and one Contact per conversion.
-   Editing a "create new" Organization or Contact updates the CRM Lead, because that is how CRM builds the
    new records.
-   Tax Category is only resolved for a GST "Composition" answer.
-   Deal step fields follow CRM's own layout and pickers.

## Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository before committing.

## License

MIT
