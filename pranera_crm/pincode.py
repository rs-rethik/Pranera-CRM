"""State and city for an Indian pincode, so the deal wizard's sales person picks instead of typing.

- State: India Compliance's pincode ranges (offline), the same table it validates an Address against.
- City: India Post's public pincode API (the post offices' district), else the cities this site's
  own Addresses already use with that pincode, most used first.
"""

import re

import frappe
import requests
from frappe import _
from frappe.query_builder.functions import Count
from frappe.rate_limiter import rate_limit

PINCODE_FORMAT = re.compile(r"^[1-9][0-9]{5}$")
INDIA_POST_URL = "https://api.postalpincode.in/pincode/{0}"
INDIA_POST_TIMEOUT = 3
CACHE_PREFIX = "pranera_crm_pincode_"
CACHE_TTL = 30 * 86400
MAX_CITIES = 8


def india_states() -> list[str]:
	"""Indian states and union territories as India Compliance names them (empty without it)."""
	try:
		from india_compliance.gst_india.constants import STATE_NUMBERS
	except ImportError:
		return []
	return sorted(state for state in STATE_NUMBERS if state != "Other Territory")


def states_for_pincode(pincode: str) -> list[str]:
	"""The states whose pincode ranges hold this pincode: usually one (Chandigarh shares with Punjab)."""
	try:
		from india_compliance.gst_india.constants import STATE_PINCODE_MAPPING
	except ImportError:
		return []
	prefix = int(pincode[:3])
	found = []
	for state, ranges in STATE_PINCODE_MAPPING.items():
		if not isinstance(ranges[0], tuple):
			ranges = (ranges,)
		if any(low <= prefix <= high for low, high in ranges):
			found.append(state)
	return found


# read-only; POST too because frappe-ui's call() posts
@frappe.whitelist(methods=["GET", "POST"])
@rate_limit(limit=60, seconds=300)
def pincode_details(pincode: str) -> dict:
	"""{"state", "states", "country", "cities", "source"} for the wizard's address. ``state`` is set only
	when the pincode belongs to one state; ``cities`` is best first and may be empty (then it's typed)."""
	frappe.has_permission("Address", "read", throw=True)
	pincode = (pincode or "").strip()
	if not PINCODE_FORMAT.match(pincode):
		frappe.throw(_("{0} is not a valid 6-digit pincode.").format(frappe.bold(pincode)))

	states = states_for_pincode(pincode)
	used = _site_cities(pincode)
	cities = _rank_post_names(_india_post_names(pincode, states), used)
	source = "india_post" if cities else ("addresses" if used else "")
	cities += [name for name in used if name.casefold() not in {c.casefold() for c in cities}]
	return {
		"pincode": pincode,
		"state": states[0] if len(states) == 1 else "",
		"states": states,
		"country": "India",
		"cities": cities[:MAX_CITIES],
		"source": source,
	}


def _india_post_names(pincode: str, states: list[str]) -> list[list]:
	"""[district, block] of each post office with this pincode, cached for a month. Both are kept: India
	Post still files some towns under their old district (Tiruppur's offices say District "Coimbatore",
	Block "Tiruppur"). [] when India Post is down or slow."""
	key = CACHE_PREFIX + pincode
	cached = frappe.cache.get_value(key, expires=True)
	if cached is not None:
		return cached
	try:
		# India Post resets connections from the default python-requests User-Agent
		response = requests.get(
			INDIA_POST_URL.format(pincode), timeout=INDIA_POST_TIMEOUT, headers={"User-Agent": "Frappe"}
		)
		response.raise_for_status()
		body = response.json()
	except (requests.RequestException, ValueError):
		# an outside free service: the site's own addresses stand in, nothing to report
		return []

	result = body[0] if isinstance(body, list) and body else {}
	offices = (result.get("PostOffice") or []) if result.get("Status") == "Success" else []
	wanted = {state.casefold() for state in states}
	names = [
		[office.get("District") or "", office.get("Block") or ""]
		for office in offices
		if not wanted or (office.get("State") or "").casefold() in wanted
	]
	frappe.cache.set_value(key, names, expires_in_sec=CACHE_TTL)
	return names


def _rank_post_names(names: list[list], used: dict[str, int]) -> list[str]:
	"""India Post's district and block names, the ones this site's addresses use most with the pincode
	first, then districts before blocks, then by how many post offices name them."""
	uses_of = {name.casefold(): count for name, count in used.items()}
	score: dict[str, tuple] = {}
	labels: dict[str, str] = {}
	for district, block in names:
		for weight, name in ((2, district), (1, block)):
			label = _clean(name)
			if not label or label.casefold() == "na":
				continue
			key = label.casefold()
			labels.setdefault(key, label)
			uses, kind, posts = score.get(key, (uses_of.get(key, 0), 0, 0))
			score[key] = (uses, max(kind, weight), posts + 1)
	return [labels[key] for key in sorted(score, key=lambda k: score[k], reverse=True)]


def _site_cities(pincode: str) -> dict[str, int]:
	"""{city: uses} for this site's Addresses with the pincode, spellings merged, most used first."""
	address = frappe.qb.DocType("Address")
	rows = (
		frappe.qb.from_(address)
		.select(address.city, Count(address.name).as_("uses"))
		.where((address.pincode == pincode) & address.city.isnotnull() & (address.city != ""))
		.groupby(address.city)
		.orderby(Count(address.name), order=frappe.qb.desc)
		.limit(50)
	).run(as_dict=True)
	uses: dict[str, int] = {}
	labels: dict[str, str] = {}
	for row in rows:
		label = _clean(row.city)
		if label:
			key = label.casefold()
			labels.setdefault(key, label)
			uses[key] = uses.get(key, 0) + row.uses
	return {labels[key]: uses[key] for key in sorted(uses, key=lambda k: -uses[k])}


def _clean(name: str | None) -> str:
	"""Trimmed, single-spaced, and title case when typed all upper or all lower ("TIRUPUR, " → "Tirupur")."""
	clean = re.sub(r"\s+", " ", (name or "").strip(" ,.;-\t\n")).strip()
	return clean.title() if clean.isupper() or clean.islower() else clean
