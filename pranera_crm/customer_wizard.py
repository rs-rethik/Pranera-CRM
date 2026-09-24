"""Resolution engine for ``Customer Wizard Mapping``: turns a set of plain-language
question answers into the actual field values to write on Customer / Address / Contact.

Nothing about the questions, their answers, or the values they map to is hardcoded
here — all of that lives in the ``Customer Wizard Mapping`` doctype. This module only
implements the *rules* by which answers become values:

- **Fixed** questions: the chosen answer's row supplies ``mapped_value`` (or nothing,
  see "overlay" below).
- **Dynamic** questions: the answer *is* a live record name from ``source_doctype``.
- **Branching**: a question is only visible once its ``depends_on_question`` was
  answered the right way — ``depends_on_operator`` ``Is`` (default) matches one
  answer, ``Is not`` matches every other answer of the parent.
- **Overlay**: visible questions are applied in ``sequence`` order; a question whose
  chosen answer has no ``mapped_value`` contributes nothing and leaves whatever an
  earlier question already wrote for that field alone. This is how two independent
  follow-up questions (e.g. "Regular or Composition?" and "Is it an SEZ unit?") can
  combine onto the same field without a multi-answer combinator.
- **Fallback**: a visible-but-unanswered question with no auto-selected default
  applies its ``fallback_value`` and is flagged for the Review step.
- **Mandatory**: a question flagged ``is_mandatory`` that resolves nothing (no
  answer, default, fallback or override) blocks submission with a clear error.

Sales Person is special-cased: a question targeting ``Customer.sales_team`` (a child
table) doesn't set a plain field, it names the Sales Person(s) to add as a
100%-allocated ``Sales Team`` row.

A question flagged ``requires_erpnext_bridge`` is only asked/resolved when the
ERPNext Customer bridge applies to this call (``include_bridge_questions=True``,
the default) — pass ``False`` to resolve only the questions that apply regardless
of the bridge (e.g. Territory, Industry), such as before the ERPNext bridge has
even run. A ``secondary_target_doctype``/``secondary_target_fieldname`` pair lets
one Fixed question's answer also write a *second* field (its option's
``secondary_mapped_value``) — used when the same real-world answer (e.g. "where is
the customer located?") has to land on two different doctypes with two different
valid values (CRM Organization's own Territory vs. ERPNext's Customer Territory).
"""

import json
import re

import frappe
from frappe import _

SALES_TEAM_TARGET = ("Customer", "sales_team")
PLACEHOLDER = re.compile(r"\{\{\s*answers\.([a-zA-Z0-9_]+)\s*\}\}")


def get_questions(scope: str, *, include_bridge_questions: bool = True) -> list[dict]:
	"""All enabled questions for a wizard step, in resolution/display order.

	``include_bridge_questions=False`` excludes questions flagged
	``requires_erpnext_bridge`` — used when resolving/rendering outside the
	ERPNext Customer bridge (it's off site-wide, or declined for this
	conversion), so an ERPNext-only question is never shown, resolved, or
	mandatory-checked in that context.
	"""
	filters = {"scope": scope, "enabled": 1}
	if not include_bridge_questions:
		filters["requires_erpnext_bridge"] = 0
	names = frappe.get_all(
		"Customer Wizard Mapping",
		filters=filters,
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
	if not question.enabled:
		return False
	if not question.depends_on_question:
		return True
	parent = frappe.get_cached_doc("Customer Wizard Mapping", question.depends_on_question)
	if not is_visible(parent, answers):
		return False
	given = answers.get(parent.question_key)
	if given is None:
		given = default_answer(parent)
	if given is None:
		return False
	matches = given == question.depends_on_option
	return not matches if question.depends_on_operator == "Is not" else matches


def visible_questions(scope: str, answers: dict, *, include_bridge_questions: bool = True) -> list:
	return [
		q
		for q in get_questions(scope, include_bridge_questions=include_bridge_questions)
		if is_visible(q, answers)
	]


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


def resolve(
	scope: str,
	answers: dict,
	overrides: dict | None = None,
	*,
	user: str | None = None,
	include_bridge_questions: bool = True,
) -> dict:
	"""Resolve every visible question for ``scope``.

	Returns ``{"fields": {doctype: {fieldname: value}}, "sales_persons": [name, ...],
	"review": [row, ...]}``. ``review`` rows are always in question order and safe to
	show to the user; ``fields``/``sales_persons`` are what the caller should actually
	write. Overrides are only applied when the acting user holds one of the question's
	``override_roles`` — silently ignored otherwise (never trust the client).

	``include_bridge_questions=False`` skips ``requires_erpnext_bridge`` questions
	entirely (see ``get_questions``) — pass this when resolving outside the ERPNext
	Customer bridge so an unrelated ERPNext-only mandatory question can't block it.
	"""
	answers = answers or {}
	overrides = overrides or {}
	user_roles = set(frappe.get_roles(user or frappe.session.user))

	fields: dict[str, dict[str, str]] = {}
	sales_persons: list[str] = []
	review = []

	for question in visible_questions(scope, answers, include_bridge_questions=include_bridge_questions):
		can_override = bool(user_roles & set(question.get_override_roles()))
		given = answers.get(question.question_key)
		if given == "":
			given = None
		auto = given is None
		if auto:
			given = default_answer(question)

		if question.question_type == "Fixed":
			option = _option_row(question, given) if given is not None else None
			if given is not None and option is None:
				frappe.throw(
					_("{0}: \"{1}\" is not one of the available answers").format(question.label, given),
					title=_("Invalid Answer"),
				)
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

		overridden = can_override and question.question_key in overrides
		if overridden:
			value = overrides[question.question_key] or None
			answer_label = _("{0} (overridden)").format(value) if value else answer_label

		if question.is_mandatory and given is None and value is None:
			frappe.throw(
				_("{0}: please answer this question before submitting").format(question.label),
				title=_("Answer Required"),
			)

		if value:
			if (question.target_doctype, question.target_fieldname) == SALES_TEAM_TARGET:
				sales_persons.append(value)
			else:
				fields.setdefault(question.target_doctype, {})[question.target_fieldname] = value

		if question.secondary_target_doctype and question.question_type == "Fixed" and option and not overridden:
			secondary_value = option.secondary_mapped_value
			if secondary_value:
				fields.setdefault(question.secondary_target_doctype, {})[
					question.secondary_target_fieldname
				] = secondary_value

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
		return json.dumps(value or "")[1:-1]

	rendered = PLACEHOLDER.sub(sub, source_filters)
	parsed = json.loads(rendered)
	return parsed if isinstance(parsed, dict) else {}


def default_answer_by_key(question_key: str):
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
	try:
		rows = frappe.get_list(
			question.source_doctype,
			filters=filters,
			fields=fields,
			order_by=f"{label_field} asc",
			limit_page_length=100,
		)
	except frappe.PermissionError:
		return []
	return [{"label": r.get(label_field) or r.name, "value": r.name} for r in rows]


def question_payload(question, answers: dict, *, user: str | None = None) -> dict:
	"""Everything the frontend needs to render one question.

	Includes the target field's meta and each answer's ``mapped_value`` so the
	Review step can show the *resolved ERPNext values* (and offer the right
	override control) without asking the server again. Display-only: the server
	re-resolves and re-validates everything at submit time.
	"""
	user_roles = set(frappe.get_roles(user or frappe.session.user))
	target_label, target_fieldtype, target_field_options = _target_field_meta(question)
	payload = {
		"question_key": question.question_key,
		"label": question.label,
		"target_doctype": question.target_doctype,
		"target_fieldname": question.target_fieldname,
		"target_label": target_label,
		"target_fieldtype": target_fieldtype,
		"target_field_options": target_field_options,
		"question_type": question.question_type,
		"depends_on_question": question.depends_on_question,
		"depends_on_option": question.depends_on_option,
		"depends_on_operator": question.depends_on_operator or "Is",
		"is_mandatory": bool(question.is_mandatory),
		"requires_erpnext_bridge": bool(question.requires_erpnext_bridge),
		"fallback_value": question.fallback_value or None,
		"can_override": bool(user_roles & set(question.get_override_roles())),
	}
	if question.question_type == "Fixed":
		payload["options"] = [
			{
				"label": o.option_label,
				"value": o.option_value,
				"mapped_value": o.mapped_value or None,
				"is_default": bool(o.is_default),
			}
			for o in question.options
		]
		payload["default"] = default_answer(question)
	else:
		payload["options"] = resolve_dynamic_options(question, answers)
		payload["default"] = None
	return payload


def _target_field_meta(question) -> tuple[str, str, str | None]:
	"""(label, fieldtype, options) of the target field, for the Review step's
	value display and override control. The Sales Team special target renders as
	a Sales Person link."""
	if (question.target_doctype, question.target_fieldname) == SALES_TEAM_TARGET:
		return _("Sales Person"), "Link", "Sales Person"
	field = frappe.get_meta(question.target_doctype).get_field(question.target_fieldname)
	if not field:
		return question.target_fieldname.replace("_", " ").title(), "Data", None
	label = _(field.label) if field.label else question.target_fieldname
	return label, field.fieldtype, field.options or None


def all_questions_payload(
	scope: str,
	answers: dict | None = None,
	*,
	user: str | None = None,
	include_bridge_questions: bool = True,
) -> list[dict]:
	"""Every enabled question for a step, regardless of current visibility — what
	`get_wizard_context` sends at page load. The client (``lib/questions.js``)
	does its own branching visibility from this full list as the user answers, so
	a follow-up question only reachable through a later answer is still present
	for it to reveal; ``resolve()``/``scope_payload`` remain the visibility-filtered
	view used server-side at submit time."""
	return [
		question_payload(q, answers or {}, user=user)
		for q in get_questions(scope, include_bridge_questions=include_bridge_questions)
	]


def scope_payload(
	scope: str, answers: dict, *, user: str | None = None, include_bridge_questions: bool = True
) -> list[dict]:
	"""Visible questions for a step, each with its live options — used to re-resolve
	Dynamic options as answers change (``pranera_crm.erpnext_customer.refresh_questions``)
	and at submit time; NOT what the initial page render should use (see
	``all_questions_payload``)."""
	return [
		question_payload(q, answers, user=user)
		for q in visible_questions(scope, answers, include_bridge_questions=include_bridge_questions)
	]
