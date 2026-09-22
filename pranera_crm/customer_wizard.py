"""Resolution engine for ``Customer Wizard Mapping``: turns a set of plain-language
question answers into the actual field values to write on Customer / Address / Contact.

Nothing about the questions, their answers, or the values they map to is hardcoded
here — all of that lives in the ``Customer Wizard Mapping`` doctype. This module only
implements the *rules* by which answers become values:

- **Fixed** questions: the chosen answer's row supplies ``mapped_value`` (or nothing,
  see "overlay" below).
- **Dynamic** questions: the answer *is* a live record name from ``source_doctype``.
- **Branching**: a question is only visible once its ``depends_on_question`` was
  answered with ``depends_on_option``.
- **Overlay**: visible questions are applied in ``sequence`` order; a question whose
  chosen answer has no ``mapped_value`` contributes nothing and leaves whatever an
  earlier question already wrote for that field alone. This is how two independent
  follow-up questions (e.g. "Regular or Composition?" and "Is it an SEZ unit?") can
  combine onto the same field without a multi-answer combinator.
- **Fallback**: a visible-but-unanswered question with no auto-selected default
  applies its ``fallback_value`` and is flagged for the Review step.

Sales Person is special-cased: a question targeting ``Customer.sales_team`` (a child
table) doesn't set a plain field, it names the Sales Person(s) to add as a
100%-allocated ``Sales Team`` row.
"""

import json
import re

import frappe
from frappe import _

SALES_TEAM_TARGET = ("Customer", "sales_team")
PLACEHOLDER = re.compile(r"\{\{\s*answers\.([a-zA-Z0-9_]+)\s*\}\}")


def get_questions(scope: str) -> list[dict]:
	"""All enabled questions for a wizard step, in resolution/display order."""
	names = frappe.get_all(
		"Customer Wizard Mapping",
		filters={"scope": scope, "enabled": 1},
		order_by="sequence asc, question_key asc",
		pluck="name",
	)
	return [frappe.get_cached_doc("Customer Wizard Mapping", n) for n in names]


def default_answer(question) -> str | None:
	"""The answer key that applies with no user interaction, if any."""
	if question.question_type != "Fixed":
		return None
	options = [o for o in question.options]
	if not options:
		return None
	defaults = [o.option_value for o in options if o.is_default]
	if defaults:
		return defaults[0]
	if len(options) == 1:
		return options[0].option_value
	return None


def is_visible(question, answers: dict) -> bool:
	if not question.depends_on_question:
		return True
	parent = frappe.get_cached_doc("Customer Wizard Mapping", question.depends_on_question)
	if not is_visible(parent, answers):
		return False
	given = answers.get(parent.question_key)
	if given is None:
		given = default_answer(parent)
	return given == question.depends_on_option


def visible_questions(scope: str, answers: dict) -> list:
	return [q for q in get_questions(scope) if is_visible(q, answers)]


def _option_row(question, value):
	for row in question.options:
		if row.option_value == value:
			return row
	return None


def _dynamic_label(question, value):
	if not value:
		return None
	label_field = question.source_label_field or "name"
	try:
		return frappe.db.get_value(question.source_doctype, value, label_field) or value
	except Exception:
		return value


def resolve(scope: str, answers: dict, overrides: dict | None = None, *, user: str | None = None) -> dict:
	"""Resolve every visible question for ``scope``.

	Returns ``{"fields": {doctype: {fieldname: value}}, "sales_persons": [name, ...],
	"review": [row, ...]}``. ``review`` rows are always in question order and safe to
	show to the user; ``fields``/``sales_persons`` are what the caller should actually
	write. Overrides are only applied when the acting user holds one of the question's
	``override_roles`` — silently ignored otherwise (never trust the client).
	"""
	answers = answers or {}
	overrides = overrides or {}
	user_roles = set(frappe.get_roles(user or frappe.session.user))

	fields: dict[str, dict[str, str]] = {}
	sales_persons: list[str] = []
	review = []

	for question in visible_questions(scope, answers):
		can_override = bool(user_roles & set(question.get_override_roles()))
		given = answers.get(question.question_key)
		auto = given is None
		if auto:
			given = default_answer(question)

		if question.question_type == "Fixed":
			option = _option_row(question, given) if given is not None else None
			answer_label = option.option_label if option else None
			value = option.mapped_value if option else None
		else:
			answer_label = _dynamic_label(question, given)
			value = given or None

		was_fallback = False
		if value is None and given is None and question.fallback_value:
			value = question.fallback_value
			answer_label = _("Default")
			was_fallback = True

		if can_override and question.question_key in overrides:
			value = overrides[question.question_key] or None
			answer_label = _("{0} (overridden)").format(value) if value else answer_label

		if value:
			if (question.target_doctype, question.target_fieldname) == SALES_TEAM_TARGET:
				sales_persons.append(value)
			else:
				fields.setdefault(question.target_doctype, {})[question.target_fieldname] = value

		review.append(
			{
				"question_key": question.question_key,
				"label": question.label,
				"answer": answer_label,
				"value": value,
				"was_fallback": was_fallback,
				"auto_answered": auto and not was_fallback and given is not None,
				"target_doctype": question.target_doctype,
				"target_fieldname": question.target_fieldname,
				"can_override": can_override,
			}
		)

	return {"fields": fields, "sales_persons": sales_persons, "review": review}


def _interpolate_filters(source_filters: str, answers: dict) -> dict:
	def sub(match):
		key = match.group(1)
		value = answers.get(key, default_answer_by_key(key))
		return json.dumps(value or "")[1:-1]  # inline the raw string, keep valid JSON quoting

	rendered = PLACEHOLDER.sub(sub, source_filters)
	parsed = json.loads(rendered)
	return parsed if isinstance(parsed, dict) else {}


def default_answer_by_key(question_key: str):
	# Placeholder resolution can reference a question that wasn't in `answers` yet
	# (e.g. re-fetching options before the user reaches that question); fall back to
	# its own default rather than leaving `{{ }}` unresolved.
	existing = frappe.db.exists("Customer Wizard Mapping", question_key)
	if not existing:
		return None
	return default_answer(frappe.get_cached_doc("Customer Wizard Mapping", question_key))


def resolve_dynamic_options(question, answers: dict) -> list[dict]:
	"""Live label/value pairs for a Dynamic question, honouring its configured filters."""
	filters = {}
	if question.source_filters:
		try:
			filters = _interpolate_filters(question.source_filters, answers)
		except (ValueError, TypeError):
			filters = {}

	label_field = question.source_label_field or "name"
	fields = ["name"] if label_field == "name" else ["name", label_field]
	rows = frappe.get_list(
		question.source_doctype,
		filters=filters,
		fields=fields,
		order_by=f"{label_field} asc",
		limit_page_length=100,
	)
	return [{"label": r.get(label_field) or r.name, "value": r.name} for r in rows]


def question_payload(question, answers: dict, *, user: str | None = None) -> dict:
	"""Everything the frontend needs to render one question."""
	user_roles = set(frappe.get_roles(user or frappe.session.user))
	payload = {
		"question_key": question.question_key,
		"label": question.label,
		"target_doctype": question.target_doctype,
		"target_fieldname": question.target_fieldname,
		"question_type": question.question_type,
		"depends_on_question": question.depends_on_question,
		"depends_on_option": question.depends_on_option,
		"can_override": bool(user_roles & set(question.get_override_roles())),
	}
	if question.question_type == "Fixed":
		payload["options"] = [
			{"label": o.option_label, "value": o.option_value, "is_default": bool(o.is_default)}
			for o in question.options
		]
		payload["default"] = default_answer(question)
	else:
		payload["options"] = resolve_dynamic_options(question, answers)
		payload["default"] = None
	return payload


def scope_payload(scope: str, answers: dict, *, user: str | None = None) -> list[dict]:
	"""Visible questions for a step, each with its live options — what `get_wizard_context` sends."""
	return [question_payload(q, answers, user=user) for q in visible_questions(scope, answers)]
