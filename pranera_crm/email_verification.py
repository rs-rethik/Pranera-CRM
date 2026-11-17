"""Email ownership check for a new Contact's email in the Convert to Deal wizard.

The address belongs to the customer, not to a Frappe ``User``, so ``frappe.twofactor``
(hard-wired to a User's email and the login flow) can't be called as-is. This reuses
its building blocks instead: a ``pyotp`` HOTP code, its email body template,
``frappe.sendmail``, ``frappe.cache`` with an expiry and ``frappe.rate_limiter``.
The sales user reads the code out of the customer and types it into the wizard.
"""

import hashlib
import secrets

import frappe
import pyotp
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.twofactor import get_email_body_for_2fa
from frappe.utils import validate_email_address

LEAD = "CRM Lead"
CODE_TTL = 300
VERIFIED_TTL = 3600
MAX_ATTEMPTS = 5
CACHE_PREFIX = "pranera_crm_email_"


class EmailNotVerified(frappe.ValidationError):
	pass


def _normalize(email) -> str:
	return (email or "").strip().lower()


def _key(kind: str, lead: str, email: str) -> str:
	digest = hashlib.sha256(f"{frappe.session.user}|{lead}|{_normalize(email)}".encode()).hexdigest()[:32]
	return f"{CACHE_PREFIX}{kind}_{digest}"


def _check_request(lead: str, email: str):
	from pranera_crm.api import _ensure_enabled

	_ensure_enabled()
	if not frappe.db.exists(LEAD, lead):
		frappe.throw(_("Lead {0} does not exist").format(lead), frappe.DoesNotExistError)
	if not frappe.has_permission(LEAD, "write", lead):
		frappe.throw(_("Not allowed to convert Lead to Deal"), frappe.PermissionError)
	if not validate_email_address(email or "", throw=False):
		frappe.throw(_("Enter a valid email address"))


def is_email_verified(lead: str, email: str) -> bool:
	return bool(frappe.cache.get_value(_key("verified", lead, email), expires=True))


def ensure_verified(lead: str, email):
	"""Raises unless ``email`` was verified for ``lead`` by the acting user. Blank is allowed."""
	if _normalize(email) and not is_email_verified(lead, email):
		frappe.throw(
			_("Verify the email address {0} before converting.").format(frappe.bold(email)),
			EmailNotVerified,
		)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=5, seconds=600)
def send_email_otp(lead: str, email: str) -> dict:
	"""Emails a one-time code to ``email``. The code is never returned to the caller."""
	_check_request(lead, email)

	secret = pyotp.random_base32()
	counter = secrets.randbelow(10**6)
	code = pyotp.HOTP(secret).at(counter)
	issuer = frappe.db.get_single_value("System Settings", "otp_issuer_name") or "Pranera CRM"

	try:
		frappe.sendmail(
			recipients=email.strip(),
			subject=_("Email Verification Code from {0}").format(issuer),
			message=get_email_body_for_2fa({"otp": code, "otp_issuer": issuer}),
			header=[_("Verification Code"), "blue"],
			delayed=False,
			retry=3,
		)
	except Exception:
		frappe.log_error(title="Pranera CRM: verification email failed")
		frappe.throw(_("Could not send the verification email. Check that outgoing email is set up."))

	frappe.cache.delete_value(_key("verified", lead, email))
	frappe.cache.set_value(
		_key("otp", lead, email),
		{"secret": secret, "counter": counter, "attempts": 0},
		expires_in_sec=CODE_TTL,
	)
	return {"sent": True}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=20, seconds=600)
def verify_email_otp(lead: str, email: str, otp: str) -> dict:
	"""Checks the code typed into the wizard; on success marks ``email`` verified for ``lead``."""
	_check_request(lead, email)

	key = _key("otp", lead, email)
	state = frappe.cache.get_value(key, expires=True)
	if not state:
		frappe.throw(_("The code has expired. Click Verify Email to get a new one."))

	if pyotp.HOTP(state["secret"]).verify((otp or "").strip(), state["counter"]):
		frappe.cache.delete_value(key)
		frappe.cache.set_value(_key("verified", lead, email), 1, expires_in_sec=VERIFIED_TTL)
		return {"verified": True}

	state["attempts"] += 1
	if state["attempts"] >= MAX_ATTEMPTS:
		frappe.cache.delete_value(key)
		frappe.throw(_("Too many incorrect attempts. Click Verify Email to get a new code."))
	frappe.cache.set_value(key, state, expires_in_sec=CODE_TTL)
	frappe.throw(_("Incorrect verification code"))
