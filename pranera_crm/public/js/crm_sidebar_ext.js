/**
 * Adds a "Deal Dashboard" item to Frappe CRM's sidebar. The dashboard opens in a panel
 * over CRM's content area, so the CRM sidebar stays in place.
 *
 * Loaded on every /crm page by pranera_crm/www/crm.html, which overrides CRM's
 * page without changing it. The crm app itself is never modified, so this file
 * works on CRM's *rendered* sidebar markup: the selectors and classes it relies
 * on are all in MARKUP below - if a CRM / frappe-ui update changes them, the
 * item just doesn't show up (CRM keeps working) and MARKUP is what to fix.
 */
(() => {
	const DASHBOARD_URL = "/deal_wizard/dashboard";
	const DASHBOARD_KEY = "dashboard";

	const MARKUP = {
		sidebar: '[data-slot="sidebar"]',
		item: '[data-slot="sidebar-item"]',
		// the template for our item; it goes at the end of this item's scroll box
		anchorLink: 'a[href^="/crm/call-logs"]',
		scrollBox: ".overflow-y-auto",
		iconSlot: "span.grid",
		labelText: ".truncate",
		suffix: '[data-slot="sidebar-item-suffix"]',
		notificationsItem: "#notifications-btn",
		// frappe-ui SidebarItem's active / inactive row classes
		activeClasses: ["bg-surface-elevation-3", "text-ink-gray-8", "shadow-sm"],
		inactiveClasses: ["text-ink-gray-6", "hover:bg-surface-gray-2"],
		// below this width the sidebar is collapsed to icons
		collapsedWidth: 100,
	};

	// lucide "chart-column"
	const ICON_ATTRS =
		'xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="size-4 text-ink-gray-7" aria-hidden="true"';
	const CHART_ICON = `<svg ${ICON_ATTRS}><path d="M3 3v16a2 2 0 0 0 2 2h16"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>`;

	const MOBILE_WIDTH = 640;
	const OPEN_CLASS = "pranera-panel-open";
	const t = (text) => window.translated_messages?.[text] || text;
	const DASHBOARD_LABEL = t("Deal Dashboard");

	let panel = null;
	let frame = null;
	let panelSidebar = null;
	let activeKey = null; // null = panel closed
	let panelQuery = ""; // the dashboard's filters, as a query string
	const sidebarResize = new ResizeObserver(() => positionPanel());
	// collapsing animates the sidebar's width after its classes change, so the section
	// item is rebuilt once the width settles
	const widthWatch = new ResizeObserver(() => ensureSection());

	// The open panel is kept in CRM's URL (?pranera_panel=dashboard) so a refresh, or a
	// copied link, comes back to it. The dashboard's filters ride along in ?pranera_q.
	// CRM's router ignores the extra params.
	const PANEL_PARAM = "pranera_panel";
	const QUERY_PARAM = "pranera_q";
	const rawReplaceState = history.replaceState.bind(history);

	function panelFromUrl() {
		const params = new URLSearchParams(location.search);
		const value = params.get(PANEL_PARAM);
		if (value === DASHBOARD_KEY) {
			return { key: DASHBOARD_KEY, url: DASHBOARD_URL, query: params.get(QUERY_PARAM) };
		}
		return null;
	}

	function stripPanel(url) {
		const parsed = new URL(url, location.origin);
		parsed.searchParams.delete(PANEL_PARAM);
		parsed.searchParams.delete(QUERY_PARAM);
		return parsed.pathname + parsed.search;
	}

	function urlWithPanel(key) {
		const params = new URLSearchParams(location.search);
		if (key === null) params.delete(PANEL_PARAM);
		else params.set(PANEL_PARAM, key);
		if (key === DASHBOARD_KEY && panelQuery) params.set(QUERY_PARAM, panelQuery);
		else params.delete(QUERY_PARAM);
		const search = params.toString();
		return location.pathname + (search ? `?${search}` : "") + location.hash;
	}

	// not history.replaceState: that one is patched below and would count as a navigation
	function writePanelToUrl(key) {
		const url = urlWithPanel(key);
		if (url !== location.pathname + location.search + location.hash) {
			rawReplaceState(history.state, "", url);
		}
		lastUrl = currentUrl();
	}

	// a panel to restore from the URL, once CRM's sidebar has rendered
	let pendingPanel = null;

	// ------------------------------------------------------------------------ //
	// Sidebar section
	// ------------------------------------------------------------------------ //

	function ensureSection() {
		for (const link of document.querySelectorAll(MARKUP.anchorLink)) {
			const sidebar = link.closest(MARKUP.sidebar);
			const refItem = link.closest(MARKUP.item);
			// only the main links section, not a pinned / public Call Logs view
			if (!sidebar || !refItem || link.closest("nav") !== sidebar.querySelector("nav"))
				continue;
			const box = refItem.closest(MARKUP.scrollBox);
			if (!box) continue;
			widthWatch.observe(sidebar);

			// Collapsing the sidebar changes the classes of CRM's items, so the item is
			// rebuilt whenever they differ from what it was built from.
			const signature = [itemSignature(refItem), isCollapsed(sidebar)].join("#");
			const existing = box.querySelector('[data-pranera="section"]');
			if (existing?.dataset.signature === signature) continue;
			existing?.remove();
			box.append(buildSection(refItem, sidebar, signature));
		}
		restorePanel();
	}

	function restorePanel() {
		if (!pendingPanel) return;
		const sidebar = document.querySelector(MARKUP.sidebar);
		if (!sidebar && !isMobile()) return;
		const { key, url, query } = pendingPanel;
		pendingPanel = null;
		panelQuery = cleanQuery(query);
		showPanel(key, url, isMobile() ? null : sidebar);
	}

	function isCollapsed(sidebar) {
		return sidebar.getBoundingClientRect().width < MARKUP.collapsedWidth;
	}

	function itemSignature(item) {
		const link = item.querySelector("a");
		return [link?.className, link?.lastElementChild?.className].join("|");
	}

	function buildSection(refItem, sidebar, signature) {
		const section = document.createElement("div");
		section.dataset.pranera = "section";
		section.dataset.signature = signature;
		const nav = document.createElement("nav");
		nav.className = "mt-1 flex flex-col gap-1";
		nav.append(buildItem(refItem, signature, DASHBOARD_KEY, DASHBOARD_LABEL, DASHBOARD_URL));
		section.append(nav);
		return section;
	}

	function buildItem(refItem, signature, key, text, url, iconSvg = CHART_ICON) {
		const item = refItem.cloneNode(true);
		item.removeAttribute("id");
		item.dataset.pranera = "item";
		item.dataset.key = key;

		const link = item.querySelector("a");
		for (const attr of ["href", "aria-current", "accesskey"]) link.removeAttribute(attr);
		link.setAttribute("role", "button");
		link.setAttribute("tabindex", "0");
		link.setAttribute("aria-label", text);
		link.title = text; // stands in for the Tooltip shown when the sidebar is collapsed
		link.style.cursor = "pointer";

		const icon = link.querySelector(MARKUP.iconSlot);
		if (icon) icon.innerHTML = iconSvg;
		const label = link.lastElementChild?.querySelector(MARKUP.labelText);
		if (label) label.textContent = text;
		item.querySelector(MARKUP.suffix)?.replaceChildren();

		setItemActive(item, key === activeKey);
		const open = (event) => {
			event.preventDefault();
			openPanel(key, url, item.closest(MARKUP.sidebar));
		};
		link.addEventListener("click", open);
		link.addEventListener("keydown", (event) => {
			if (event.key === "Enter" || event.key === " ") open(event);
		});
		return item;
	}

	function setItemActive(item, active) {
		item.dataset.state = active ? "active" : "inactive";
		item.classList.remove(...MARKUP.activeClasses, ...MARKUP.inactiveClasses);
		item.classList.add(...(active ? MARKUP.activeClasses : MARKUP.inactiveClasses));
	}

	function syncItemsState() {
		document.documentElement.classList.toggle(OPEN_CLASS, activeKey !== null);
		for (const item of document.querySelectorAll('[data-pranera="item"]')) {
			setItemActive(item, item.dataset.key === activeKey);
		}
	}

	// ------------------------------------------------------------------------ //
	// Panel
	// ------------------------------------------------------------------------ //

	function isMobile() {
		return window.innerWidth < MOBILE_WIDTH;
	}

	function openPanel(key, url, sidebar) {
		if (isMobile()) {
			// CRM's mobile sidebar is a drawer dialog that traps focus; let it close
			// (it listens for Esc) before covering the screen with the dashboard.
			document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
			setTimeout(() => showPanel(key, url, null), 250);
		} else {
			showPanel(key, url, sidebar);
		}
	}

	function showPanel(key, url, sidebar) {
		if (!panel) panel = buildPanel();
		const src = `${url}?embed=1${panelQuery ? `&${panelQuery}` : ""}`;
		// the dashboard changes its own filters: opening it again must not reload them away
		const sameDashboard = key === DASHBOARD_KEY && activeKey === DASHBOARD_KEY;
		if (!sameDashboard && frame.getAttribute("src") !== src) frame.src = src;
		sidebarResize.disconnect();
		panelSidebar = sidebar;
		if (sidebar) sidebarResize.observe(sidebar);
		activeKey = key;
		panel.hidden = false;
		positionPanel();
		syncItemsState();
		writePanelToUrl(key);
	}

	function closePanel() {
		if (activeKey === null) return;
		activeKey = null;
		panel.hidden = true;
		sidebarResize.disconnect();
		panelSidebar = null;
		syncItemsState();
		// a navigation already left the param behind; closing by Esc or the X didn't
		if (new URLSearchParams(location.search).has(PANEL_PARAM)) writePanelToUrl(null);
	}

	function buildPanel() {
		const el = document.createElement("div");
		el.id = "pranera-panel";
		el.hidden = true;

		frame = document.createElement("iframe");
		frame.title = DASHBOARD_LABEL;
		// Esc inside the dashboard doesn't bubble out of the iframe; listen there too
		// (same origin, so contentWindow is reachable).
		frame.addEventListener("load", () => {
			try {
				frame.contentWindow.addEventListener("keydown", onKeydown);
			} catch {
				// not same-origin (e.g. redirected to login elsewhere): Esc just won't work inside
			}
		});

		el.append(frame);
		document.body.append(el);
		return el;
	}

	function positionPanel() {
		if (!panel || activeKey === null) return;
		const mobile = !panelSidebar || isMobile();
		panel.classList.toggle("pranera-panel-mobile", mobile);
		panel.style.left = mobile
			? "0px"
			: `${Math.round(panelSidebar.getBoundingClientRect().right)}px`;
		// the sidebar may have collapsed / expanded: its items change with it
		ensureSection();
	}

	// ------------------------------------------------------------------------ //
	// Closing: another sidebar link, Esc, or any CRM navigation
	// ------------------------------------------------------------------------ //

	function onKeydown(event) {
		if (event.key === "Escape" && activeKey !== null) closePanel();
	}

	function onSidebarClick(event) {
		if (activeKey === null) return;
		const item = event.target.closest?.(MARKUP.item);
		if (!item || item.dataset.pranera) return;
		// links (incl. the route that's already open, which doesn't change the URL)
		// and the notifications panel; collapse / help leave the dashboard open
		if (item.querySelector("a[href]") || item.matches(MARKUP.notificationsItem)) closePanel();
	}

	const currentUrl = () => location.pathname + location.search;
	let lastUrl = currentUrl();

	function onUrlChange() {
		// vue-router also calls replaceState just to store scroll positions; only a
		// real change of page closes the dashboard
		const url = currentUrl();
		if (url === lastUrl) return;
		// vue-router rewrites the URL without our param: put it back
		if (activeKey !== null && stripPanel(url) === stripPanel(lastUrl)) {
			writePanelToUrl(activeKey);
			return;
		}
		lastUrl = url;
		closePanel();
	}

	for (const method of ["pushState", "replaceState"]) {
		const original = history[method];
		history[method] = function (...args) {
			const result = original.apply(this, args);
			onUrlChange();
			return result;
		};
	}
	window.addEventListener("popstate", onUrlChange);

	// The dashboard's filters changed: keep them in CRM's URL
	function followPanelQuery(query) {
		if (activeKey !== DASHBOARD_KEY) return;
		panelQuery = cleanQuery(query);
		writePanelToUrl(activeKey);
	}

	// only plain key=value text ever reaches the panel's URL
	function cleanQuery(query) {
		if (!query) return "";
		const params = new URLSearchParams(typeof query === "string" ? query : undefined);
		if (typeof query === "object") {
			for (const [key, value] of Object.entries(query)) {
				if (typeof value === "string") params.set(key, value);
			}
		}
		params.delete("embed");
		return params.toString();
	}

	// Messages from the dashboard (same origin only)
	window.addEventListener("message", (event) => {
		if (event.origin !== location.origin) return;
		const data = event.data;
		const type = typeof data === "string" ? data : data?.type;
		if (type === "pranera:close-panel") closePanel();
		else if (type === "pranera:panel-query") followPanelQuery(data.query);
		else if (
			type === "pranera:open-crm" &&
			typeof data.path === "string" &&
			data.path.startsWith("/crm/")
		) {
			// a record in a dashboard list: CRM's router follows the pushState + popstate
			history.pushState({}, "", data.path);
			window.dispatchEvent(new PopStateEvent("popstate", { state: {} }));
		}
	});
	window.addEventListener("resize", positionPanel);
	document.addEventListener("keydown", onKeydown);
	document.addEventListener("click", onSidebarClick, true);

	// ------------------------------------------------------------------------ //
	// Styles
	// ------------------------------------------------------------------------ //

	const style = document.createElement("style");
	style.textContent = `
    #pranera-panel {
      position: fixed; top: 0; right: 0; bottom: 0; z-index: 20;
      display: flex; flex-direction: column;
      background: var(--surface-base, #fff);
    }
    #pranera-panel[hidden] { display: none; }
    #pranera-panel iframe { flex: 1; width: 100%; border: 0; }
    #pranera-panel.pranera-panel-mobile { z-index: 60; }
    /* while the dashboard is open it is the active item, not CRM's current page */
    html.${OPEN_CLASS} ${MARKUP.item}[data-state="active"]:not([data-pranera]) {
      background-color: transparent; box-shadow: none; color: var(--ink-gray-6, #525252);
    }
  `;
	document.head.append(style);

	// ------------------------------------------------------------------------ //
	// Start: CRM renders (and re-renders) its sidebar after this script runs
	// ------------------------------------------------------------------------ //

	let scheduled = false;
	const observer = new MutationObserver(() => {
		if (scheduled) return;
		scheduled = true;
		requestAnimationFrame(() => {
			scheduled = false;
			ensureSection();
		});
	});
	observer.observe(document.body, {
		childList: true,
		subtree: true,
		attributes: true,
		attributeFilter: ["class"],
	});
	pendingPanel = panelFromUrl();
	ensureSection();
	// on a phone CRM renders no sidebar to wait for
	if (pendingPanel && isMobile()) setTimeout(restorePanel, 500);
})();
