// Client-side mirror of pranera_crm.customer_wizard: which questions are visible
// given the current answers, and what they'd resolve to. This is for instant UI
// feedback only (show/hide follow-ups, a live Review preview) — the server
// re-resolves everything from scratch at submit time and is the only thing that
// actually writes a value, so nothing here needs to be tamper-proof.

import { __ } from '@/translation'

/** The answer that applies with no interaction: the option marked default, or the
 * only option when there is exactly one. */
export function defaultAnswer(question) {
  if (question.question_type !== 'Fixed') return null
  const options = question.options || []
  if (!options.length) return null
  const marked = options.find((o) => o.is_default)
  if (marked) return marked.value
  return options.length === 1 ? options[0].value : null
}

function isVisible(question, answers, byKey) {
  if (!question.depends_on_question) return true
  const parent = byKey[question.depends_on_question]
  if (!parent || !isVisible(parent, answers, byKey)) return false
  const given = answers[parent.question_key] ?? defaultAnswer(parent)
  if (given == null) return false
  const matches = given === question.depends_on_option
  return question.depends_on_operator === 'Is not' ? !matches : matches
}

/** Questions currently shown, in the order the server sent them. */
export function visibleQuestions(questions, answers) {
  const byKey = Object.fromEntries((questions || []).map((q) => [q.question_key, q]))
  return (questions || []).filter((q) => isVisible(q, answers, byKey))
}

/**
 * Visible questions flagged mandatory that have no answer (nor a default or
 * fallback that would satisfy them) — what the step validation blocks on.
 */
export function unansweredMandatory(questions, answers) {
  return visibleQuestions(questions, answers).filter(
    (q) => q.is_mandatory && !(q.question_key in (answers || {})) && !defaultAnswer(q) && !q.fallback_value,
  )
}

/**
 * The resolved ERPNext values the Review step shows: one row per target field,
 * overlay rules mirrored from the server (visible questions in order, a later
 * question targeting the same field wins when it actually resolves a value).
 * Display-only preview — the server re-resolves at submit time.
 *
 * Returns { rows: [...], sales_persons: [...] }; each row is
 * { key, doctype, fieldname, label, value, was_fallback, overridden, can_override, question_key }.
 */
export function resolvedFields(questions, answers = {}, overrides = {}) {
  const rows = new Map()
  const salesPersons = []

  for (const question of visibleQuestions(questions, answers)) {
    const given = answers[question.question_key]
    const auto = given == null
    const effective = auto ? defaultAnswer(question) : given

    let value =
      question.question_type === 'Fixed' ? (optionFor(question, effective)?.mapped_value ?? null) : effective || null
    let wasFallback = false
    if (value == null && effective == null && question.fallback_value) {
      value = question.fallback_value
      wasFallback = true
    }

    const canOverride = !!question.can_override
    const overridden = canOverride && question.question_key in overrides
    if (overridden) value = overrides[question.question_key] || null

    const isSalesTeam = question.target_doctype === 'Customer' && question.target_fieldname === 'sales_team'
    if (isSalesTeam) {
      if (value) salesPersons.push({ value, overridden, question_key: question.question_key })
      continue
    }

    const key = `${question.target_doctype}.${question.target_fieldname}`
    // overlay: only a question that resolves a value takes over the field
    if (value == null) {
      if (!rows.has(key) && overridden) {
        // an override that empties the field: keep the row so it stays editable
        rows.set(key, emptyRow(question, overridden))
      }
      continue
    }
    rows.set(key, {
      key,
      doctype: question.target_doctype,
      fieldname: question.target_fieldname,
      label: question.target_label || question.target_fieldname,
      fieldtype: question.target_fieldtype || 'Data',
      field_options: question.target_field_options || null,
      value,
      was_fallback: wasFallback,
      overridden,
      can_override: canOverride,
      question_key: question.question_key,
    })
  }

  return { rows: [...rows.values()], sales_persons: salesPersons }
}

function emptyRow(question, overridden) {
  return {
    key: `${question.target_doctype}.${question.target_fieldname}`,
    doctype: question.target_doctype,
    fieldname: question.target_fieldname,
    label: question.target_label || question.target_fieldname,
    fieldtype: question.target_fieldtype || 'Data',
    field_options: question.target_field_options || null,
    value: null,
    was_fallback: false,
    overridden,
    can_override: !!question.can_override,
    question_key: question.question_key,
  }
}

function optionFor(question, value) {
  return (question.options || []).find((o) => o.value === value) || null
}

/**
 * A Review-step preview: one row per visible question, with the label of what was
 * (or would be) chosen. Mirrors the server's "overlay" rule (later questions
 * targeting the same field win, but only when they actually resolve a value) only
 * to the extent needed for display — it does not need to compute field values.
 */
export function reviewRows(questions, answers, overrides = {}) {
  return visibleQuestions(questions, answers).map((question) => {
    const given = answers[question.question_key]
    const auto = given == null
    const effective = auto ? defaultAnswer(question) : given

    let answerLabel =
      question.question_type === 'Fixed'
        ? (optionFor(question, effective)?.label ?? null)
        : (optionFor(question, effective)?.label ?? effective)
    let wasFallback = false
    if (effective == null && question.fallback_value) {
      answerLabel = __('Default')
      wasFallback = true
    }

    const overridden = question.can_override && question.question_key in overrides
    return {
      question_key: question.question_key,
      label: question.label,
      answer: overridden ? overrides[question.question_key] : answerLabel,
      was_fallback: wasFallback,
      auto_answered: auto && effective != null,
      can_override: !!question.can_override,
      overridden,
    }
  })
}
