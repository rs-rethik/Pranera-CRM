/**
 * Adds a country-code picker to the phone fields (options "Phone") of Frappe CRM's forms,
 * styled like Frappe Desk's Phone field: a flag + dial code button that opens a searchable
 * list of countries. A number is kept as "+91 98765 43210" instead of being typed with the
 * code by hand.
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
	// the same flag images Frappe Desk uses
	const flagUrl = (code) => `https://flagcdn.com/${code}.svg`;
	const ICON =
		'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
	const CHEVRON = `<svg ${ICON}><path d="m6 9 6 6 6-6"/></svg>`;
	const SEARCH = `<svg ${ICON}><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>`;

	let labels = new Set();
	let countries = [];
	let defaultCode = null;
	let byIsdLength = []; // countries, longest dial code first, for prefix matching

	// ------------------------------------------------------------------------ //
	// Numbers
	// ------------------------------------------------------------------------ //

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

	const countryByCode = (code) => countries.find((c) => c.code === code) || null;

	// ------------------------------------------------------------------------ //
	// The picker
	// ------------------------------------------------------------------------ //

	// The label is the field's first element in both of CRM's layouts (above the control in
	// forms and dialogs, left of it in the side panel); CRM adds a "*" after it when required.
	function labelOf(field) {
		return (field.firstElementChild?.textContent || "").replace(/\s*\*$/, "").trim();
	}

	function flagImg(code) {
		const img = document.createElement("img");
		img.src = flagUrl(code);
		img.width = 20;
		img.height = 15;
		img.alt = "";
		img.loading = "lazy";
		// offline: no flag, the dial code still says which country
		img.addEventListener("error", () => (img.style.visibility = "hidden"));
		return img;
	}

	function decorate(field) {
		if (field.dataset[MARK]) return;
		const input = field.querySelector(MARKUP.input);
		if (!input || !labels.has(labelOf(field))) return;
		field.dataset[MARK] = "1";

		const trigger = document.createElement("button");
		trigger.type = "button";
		trigger.className = "pranera-phone-trigger";
		trigger.setAttribute("aria-haspopup", "listbox");
		trigger.setAttribute("aria-label", "Country code");
		trigger.addEventListener("click", () => togglePopup(field));

		// Side panel rows are already label | control flex rows; in forms the field is
		// turned into a wrapping row (see the styles).
		const sideRow = field.classList.contains("flex");
		const host = sideRow ? field.children[1] : field;
		let control = input;
		while (control.parentElement !== host) control = control.parentElement;
		control.before(trigger);
		if (!sideRow) field.classList.add("pranera-phone-field");

		field.pranera = { trigger, chosen: "", rendered: null, popup: null, hadNumber: false };
		sync(field);
	}

	function renderTrigger(field) {
		const { trigger, chosen } = field.pranera;
		const country = countryByCode(chosen);
		trigger.replaceChildren();
		if (country) trigger.append(flagImg(country.code));
		const text = document.createElement("span");
		text.textContent = country ? country.isd : "Code";
		const chevron = document.createElement("span");
		chevron.className = "pranera-phone-chevron";
		chevron.innerHTML = CHEVRON;
		trigger.append(text, chevron);
		trigger.title = country ? `${country.name} (${country.isd})` : "";
		field.pranera.rendered = chosen;
	}

	// The box shows only the national number: the country is the button's job. The full
	// "+91 98765 43210" stays in CRM's data. CRM puts the full value back in the box whenever
	// it re-renders, so this runs again shortly after (see start).
	function sync(field) {
		const input = field.querySelector(MARKUP.input);
		const state = field.pranera;
		if (!input || !state) return;
		const country = countryOf(input.value);
		if (country) {
			state.chosen = country.code;
			state.hadNumber = true;
			// not while it is being typed in
			if (document.activeElement !== input) input.value = nationalPart(input.value, country);
		} else if (input.value.trim() === "" && state.hadNumber) {
			// the record changed to one without a number: its country is not the last one's
			state.chosen = "";
			state.hadNumber = false;
		}
		if (state.rendered !== state.chosen) renderTrigger(field);
		state.trigger.disabled = input.disabled;
	}

	/** Write a value the way a user would, so CRM's own change handler picks it up. */
	function commit(input, value) {
		input.value = value;
		input.dispatchEvent(new Event("input", { bubbles: true }));
		input.dispatchEvent(new Event("change", { bubbles: true }));
	}

	function pick(field, code) {
		const input = field.querySelector(MARKUP.input);
		const current = countryOf(input.value);
		const next = countryByCode(code);
		field.pranera.chosen = code;
		renderTrigger(field);
		const national = nationalPart(input.value, current);
		// with no number typed yet there is nothing to save: the code is added when it is
		if (national && (current || next)) commit(input, join(next, national));
		input.focus();
	}

	// A typed number gets the chosen code in front, before CRM reads the box. Capturing on
	// the document runs ahead of CRM's own listener on the input.
	document.addEventListener(
		"change",
		(event) => {
			const input = event.target;
			if (!(input instanceof HTMLInputElement) || input.closest(".pranera-phone-popup"))
				return;
			const field = input.closest(MARKUP.field);
			if (!field?.pranera) return;
			const typed = input.value.trim();
			if (typed.startsWith("+")) {
				sync(field);
				return;
			}
			const country = countryByCode(field.pranera.chosen);
			if (country && typed) input.value = join(country, typed);
		},
		true
	);

	// ------------------------------------------------------------------------ //
	// The country list
	// ------------------------------------------------------------------------ //

	let openField = null;

	function togglePopup(field) {
		const wasOpen = openField === field;
		closePopup();
		if (!wasOpen) openPopup(field);
	}

	function closePopup() {
		if (!openField) return;
		openField.pranera.popup?.remove();
		openField.pranera.popup = null;
		openField.pranera.trigger.setAttribute("aria-expanded", "false");
		openField = null;
	}

	function openPopup(field) {
		const { trigger, chosen } = field.pranera;
		const popup = document.createElement("div");
		popup.className = "pranera-phone-popup";

		const search = document.createElement("div");
		search.className = "pranera-phone-search";
		const box = document.createElement("input");
		box.type = "search";
		box.placeholder = "Search for countries...";
		box.autocomplete = "off";
		const icon = document.createElement("span");
		icon.innerHTML = SEARCH;
		search.append(icon, box);

		const list = document.createElement("div");
		list.className = "pranera-phone-list";
		list.setAttribute("role", "listbox");
		popup.append(search, list);

		let items = [];
		let active = 0;

		function render(query) {
			const q = query.trim().toLowerCase();
			const shown = countries
				.filter(
					(c) =>
						!q || c.name.toLowerCase().includes(q) || c.isd.includes(q) || c.code === q
				)
				// "india" finds India before British Indian Ocean Territory
				.sort((a, b) =>
					!q || a.name.toLowerCase().startsWith(q) === b.name.toLowerCase().startsWith(q)
						? 0
						: a.name.toLowerCase().startsWith(q)
						? -1
						: 1
				);
			list.replaceChildren();
			items = shown.map((c) => {
				const row = document.createElement("div");
				row.className = "pranera-phone-item";
				row.setAttribute("role", "option");
				const name = document.createElement("span");
				name.textContent = `${c.name} (${c.isd})`;
				row.append(flagImg(c.code), name);
				row.addEventListener("click", () => {
					closePopup();
					pick(field, c.code);
				});
				list.append(row);
				return { row, code: c.code };
			});
			setActive(q ? 0 : items.findIndex((i) => i.code === chosen));
			if (!shown.length) {
				const empty = document.createElement("div");
				empty.className = "pranera-phone-empty";
				empty.textContent = "No results found";
				list.append(empty);
			}
		}

		function setActive(index) {
			active = Math.min(Math.max(index, 0), Math.max(items.length - 1, 0));
			items.forEach((item, i) => item.row.classList.toggle("is-active", i === active));
			// not scrollIntoView: it would also scroll the dialog behind the list
			const row = items[active]?.row;
			if (row) {
				if (row.offsetTop < list.scrollTop) list.scrollTop = row.offsetTop;
				else if (row.offsetTop + row.offsetHeight > list.scrollTop + list.clientHeight)
					list.scrollTop = row.offsetTop + row.offsetHeight - list.clientHeight;
			}
		}

		box.addEventListener("input", () => render(box.value));
		popup.addEventListener("keydown", (event) => {
			if (event.key === "ArrowDown") setActive(active + 1);
			else if (event.key === "ArrowUp") setActive(active - 1);
			else if (event.key === "Enter" && items[active]) {
				closePopup();
				pick(field, items[active].code);
			} else if (event.key === "Escape") {
				closePopup();
				trigger.focus();
			} else return;
			// CRM's dialogs also listen for Esc / Enter: this key was for the list
			event.preventDefault();
			event.stopPropagation();
		});

		// Inside the field, so a dialog doesn't treat a click in the list as a click outside it
		field.append(popup);
		field.pranera.popup = popup;
		openField = field;
		trigger.setAttribute("aria-expanded", "true");
		render("");
		placePopup(popup, trigger);
		box.focus({ preventScroll: true });
	}

	// position: fixed, so no scrolling container clips the list. A dialog's panel is
	// transformed, which makes it the reference for "fixed": measure where (0, 0) lands.
	function placePopup(popup, trigger) {
		popup.style.top = "0px";
		popup.style.left = "0px";
		const origin = popup.getBoundingClientRect();
		const rect = trigger.getBoundingClientRect();
		const below = window.innerHeight - rect.bottom;
		const top =
			below >= popup.offsetHeight + 8 || below >= rect.top
				? rect.bottom + 4
				: rect.top - popup.offsetHeight - 4;
		const left = Math.min(rect.left, window.innerWidth - popup.offsetWidth - 8);
		popup.style.top = `${Math.max(8, top) - origin.top}px`;
		popup.style.left = `${Math.max(8, left) - origin.left}px`;
	}

	document.addEventListener(
		"pointerdown",
		(event) => {
			if (!openField) return;
			const { popup, trigger } = openField.pranera;
			if (!popup.contains(event.target) && !trigger.contains(event.target)) closePopup();
		},
		true
	);
	window.addEventListener("resize", closePopup);
	// scrolling the page under the list would leave it floating
	document.addEventListener(
		"scroll",
		(event) => {
			if (openField && !openField.pranera.popup.contains(event.target)) closePopup();
		},
		true
	);

	// ------------------------------------------------------------------------ //
	// Styles
	// ------------------------------------------------------------------------ //

	const style = document.createElement("style");
	style.textContent = `
		.pranera-phone-field { display: flex; flex-wrap: wrap; align-items: flex-start; column-gap: 6px; }
		.pranera-phone-field > :first-child { flex: 0 0 100%; }
		.pranera-phone-field > :not(:first-child):not(.pranera-phone-trigger):not(.pranera-phone-popup) { flex: 1 1 0; min-width: 0; }
		.pranera-phone-trigger {
			display: inline-flex; flex: 0 0 auto; align-items: center; gap: 6px; height: 1.75rem; padding: 0 0.5rem;
			border: 0; border-radius: 0.375rem; background-color: var(--surface-gray-2, #f3f3f3);
			color: var(--ink-gray-8, #171717); font: inherit; font-size: 0.875rem; font-weight: 400; cursor: pointer; white-space: nowrap;
		}
		.field.flex .pranera-phone-trigger { margin-right: 6px; }
		.pranera-phone-trigger:hover { background-color: var(--surface-gray-3, #ededed); }
		.pranera-phone-trigger:focus-visible { outline: 2px solid var(--outline-gray-3, #c0c0c0); }
		.pranera-phone-trigger:disabled { cursor: not-allowed; opacity: 0.6; }
		.pranera-phone-trigger img, .pranera-phone-item img { flex: none; border-radius: 2px; object-fit: cover; }
		.pranera-phone-chevron { display: inline-flex; color: var(--ink-gray-5, #6b6b6b); }
		.pranera-phone-popup {
			position: fixed; z-index: 100000; width: 20rem; max-width: calc(100vw - 16px); padding: 0.5rem;
			border-radius: 0.75rem; background: var(--surface-modal, var(--surface-base, #fff)); color: var(--ink-gray-8, #171717);
			box-shadow: 0 10px 30px rgba(0, 0, 0, 0.18), 0 0 0 1px rgba(0, 0, 0, 0.05); font-size: 0.8125rem;
		}
		.pranera-phone-search { position: relative; display: flex; align-items: center; margin-bottom: 0.25rem; }
		.pranera-phone-search > span { position: absolute; left: 0.625rem; display: inline-flex; color: var(--ink-gray-5, #6b6b6b); pointer-events: none; }
		.pranera-phone-search input {
			width: 100%; height: 2rem; padding: 0 0.5rem 0 2rem; border: 0; border-radius: 0.5rem;
			background: var(--surface-gray-2, #f3f3f3); color: inherit; font: inherit; outline: none;
		}
		.pranera-phone-search input:focus { box-shadow: 0 0 0 2px var(--outline-gray-3, #c0c0c0); }
		.pranera-phone-list { max-height: 14rem; overflow-y: auto; }
		.pranera-phone-item { display: flex; align-items: center; gap: 0.625rem; padding: 0.4rem 0.5rem; border-radius: 0.375rem; cursor: pointer; }
		.pranera-phone-item.is-active, .pranera-phone-item:hover { background: var(--surface-gray-2, #f3f3f3); }
		.pranera-phone-empty { padding: 0.75rem; text-align: center; color: var(--ink-gray-5, #6b6b6b); }
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
		// CRM sets a box's value without an event when a record loads or re-renders: catch up
		setInterval(scan, 120);
		scan();
	}

	start();
})();
