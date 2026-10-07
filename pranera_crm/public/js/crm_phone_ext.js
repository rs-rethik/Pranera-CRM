/**
 * Adds a country-code picker to the phone fields (options "Phone") of Frappe CRM's forms,
 * so a number is kept as "+91 98765 43210" instead of being typed with the code by hand.
 *
 * Loaded on every /crm page by pranera_crm/www/crm.html. CRM draws these fields as plain
 * text boxes and its rendered markup carries no fieldname, so the fields are found by
 * their label (pranera_crm.phone.get_phone_picker_data lists them) and the page is
 * never changed in the crm app. The selectors are all in MARKUP: if a CRM update changes
 * them, the pickers just don't appear and CRM keeps working.
 */
(() => {
	const API = "/api/method/pranera_crm.phone.get_phone_picker_data";
	const MARKUP = {
		field: ".field",
		input: 'input[type="text"], input:not([type])',
	};
	// who gets a shared dial code when the site's country isn't one of them
	const SHARED_CODES = { "+1": "us", "+7": "ru", "+44": "gb", "+61": "au", "+47": "no" };
	const MARK = "praneraPhone";

	let labels = new Set();
	let countries = [];
	let defaultCode = null;
	let byIsdLength = []; // countries, longest dial code first, for prefix matching

	// ------------------------------------------------------------------------ //
	// Numbers
	// ------------------------------------------------------------------------ //

	const flag = (code) =>
		String.fromCodePoint(...[...code.toUpperCase()].map((c) => 0x1f1a5 + c.charCodeAt(0)));

	/** The country whose dial code starts the number ("+9198.." -> India), or null. */
	function countryOf(value) {
		const compact = value.replace(/[\s()-]/g, "");
		if (!compact.startsWith("+")) return null;
		const matches = byIsdLength.filter((c) => compact.startsWith(c.isd));
		if (!matches.length) return null;
		const longest = matches[0].isd.length;
		const same = matches.filter((c) => c.isd.length === longest);
		// a dial code shared by several countries: the site's own, then the best known
		return (
			same.find((c) => c.code === defaultCode) ||
			same.find((c) => c.code === SHARED_CODES[c.isd]) ||
			same[0]
		);
	}

	/** The number without its dial code ("+91 98765 43210" -> "98765 43210"). */
	function nationalPart(value, country) {
		const text = value.trim();
		if (!country || !text.startsWith("+")) return text;
		const digits = country.isd.replace(/\D/g, "");
		let index = 1;
		let matched = 0;
		while (index < text.length && matched < digits.length) {
			if (/\d/.test(text[index])) matched++;
			index++;
		}
		return text.slice(index).replace(/^[\s()-]+/, "");
	}

	const join = (country, national) =>
		country && national ? `${country.isd} ${national}` : national;

	// ------------------------------------------------------------------------ //
	// The picker
	// ------------------------------------------------------------------------ //

	// The label is the field's first element in both of CRM's layouts (above the control in
	// forms and dialogs, left of it in the side panel); CRM adds a "*" after it when required.
	function labelOf(field) {
		return (field.firstElementChild?.textContent || "").replace(/\s*\*$/, "").trim();
	}

	function decorate(field) {
		if (field.dataset[MARK]) return;
		const input = field.querySelector(MARKUP.input);
		if (!input || !labels.has(labelOf(field))) return;

		field.dataset[MARK] = "1";

		const select = document.createElement("select");
		select.className = "pranera-phone-select";
		select.setAttribute("aria-label", "Country code");
		select.append(new Option("Code", ""));
		for (const c of countries) {
			select.append(new Option(`${flag(c.code)} ${c.isd}`, c.code));
			select.lastChild.title = `${c.name} (${c.isd})`;
		}
		select.addEventListener("change", () => onPick(field, select));

		// Side panel rows are already label | control flex rows; in forms the field is
		// turned into a wrapping row (see the styles).
		const sideRow = field.classList.contains("flex");
		const host = sideRow ? field.children[1] : field;
		let control = input;
		while (control.parentElement !== host) control = control.parentElement;
		control.before(select);
		if (!sideRow) field.classList.add("pranera-phone-field");
		field.pranera = { select, chosen: "" };
		sync(field);
	}

	function sync(field) {
		const input = field.querySelector(MARKUP.input);
		const { select } = field.pranera || {};
		if (!input || !select) return;
		const fromValue = countryOf(input.value);
		if (fromValue) field.pranera.chosen = fromValue.code;
		if (select.value !== field.pranera.chosen) select.value = field.pranera.chosen;
		select.disabled = input.disabled;
	}

	/** Write a value the way a user would, so CRM's own change handler picks it up. */
	function commit(input, value) {
		input.value = value;
		input.dispatchEvent(new Event("input", { bubbles: true }));
		input.dispatchEvent(new Event("change", { bubbles: true }));
	}

	function onPick(field, select) {
		const input = field.querySelector(MARKUP.input);
		const current = countryOf(input.value);
		const next = countries.find((c) => c.code === select.value) || null;
		field.pranera.chosen = select.value;
		const national = nationalPart(input.value, current);
		// with no number typed yet there is nothing to save: the code is added when it is
		if (national && (current || next)) commit(input, join(next, national));
	}

	// A typed number gets the chosen code in front, before CRM reads the box. Capturing on
	// the document runs ahead of CRM's own listener on the input.
	document.addEventListener(
		"change",
		(event) => {
			const input = event.target;
			if (!(input instanceof HTMLInputElement)) return;
			const field = input.closest(MARKUP.field);
			if (!field?.pranera || input.closest("select")) return;
			const typed = input.value.trim();
			if (typed.startsWith("+")) {
				sync(field);
				return;
			}
			const country = countries.find((c) => c.code === field.pranera.chosen);
			if (country && typed) input.value = join(country, typed);
		},
		true
	);

	// ------------------------------------------------------------------------ //
	// Styles
	// ------------------------------------------------------------------------ //

	const style = document.createElement("style");
	style.textContent = `
		.pranera-phone-field { display: flex; flex-wrap: wrap; align-items: flex-start; column-gap: 6px; }
		.pranera-phone-field > .mb-2 { flex: 0 0 100%; }
		.pranera-phone-field > :not(.mb-2):not(.pranera-phone-select) { flex: 1 1 0; min-width: 0; }
		.pranera-phone-select {
			flex: 0 0 auto; width: 5.5rem; height: 1.75rem; padding: 0 0.25rem; border: 0; border-radius: 0.375rem;
			background-color: var(--surface-gray-2, #f3f3f3); color: var(--ink-gray-8, #171717);
			font: inherit; font-size: 0.875rem; font-weight: 400; cursor: pointer;
		}
		.field.flex > * > .pranera-phone-select, .field.flex > .pranera-phone-select { margin-right: 6px; }
		.pranera-phone-select:focus-visible { outline: 2px solid var(--outline-gray-3, #c0c0c0); }
		.pranera-phone-select:disabled { cursor: not-allowed; opacity: 0.6; }
	`;
	document.head.append(style);

	// ------------------------------------------------------------------------ //
	// Start: CRM renders (and re-renders) its forms after this script runs
	// ------------------------------------------------------------------------ //

	function scan() {
		for (const field of document.querySelectorAll(MARKUP.field)) {
			if (field.dataset[MARK]) sync(field);
			else decorate(field);
		}
	}

	async function start() {
		try {
			const res = await fetch(API, {
				credentials: "same-origin",
				headers: { Accept: "application/json" },
			});
			if (!res.ok) return;
			const data = (await res.json()).message;
			labels = new Set(data.labels);
			countries = data.countries;
			defaultCode = data.default_country;
		} catch {
			return; // offline or not allowed: CRM's plain boxes stay
		}
		byIsdLength = [...countries].sort((a, b) => b.isd.length - a.isd.length);

		let scheduled = false;
		new MutationObserver(() => {
			if (scheduled) return;
			scheduled = true;
			requestAnimationFrame(() => {
				scheduled = false;
				scan();
			});
		}).observe(document.body, { childList: true, subtree: true });
		// CRM sets a box's value without an event when a record loads: catch up now and then
		setInterval(scan, 700);
		scan();
	}

	start();
})();
