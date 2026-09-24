import { describe, expect, it } from 'vitest'
import {
  defaultAnswer,
  descendantKeys,
  resolvedFields,
  reviewRows,
  unansweredMandatory,
  visibleQuestions,
} from '@/lib/questions'

const fixed = (overrides = {}) => ({
  question_key: 'q1',
  label: 'Question?',
  question_type: 'Fixed',
  options: [
    { label: 'Yes', value: 'yes' },
    { label: 'No', value: 'no' },
  ],
  can_override: false,
  ...overrides,
})

describe('defaultAnswer', () => {
  it('is null with no options or a Dynamic question', () => {
    expect(defaultAnswer(fixed({ options: [] }))).toBeNull()
    expect(defaultAnswer({ question_type: 'Dynamic', options: [{ label: 'A', value: 'a' }] })).toBeNull()
  })

  it('picks the option marked default', () => {
    const q = fixed({ options: [{ label: 'A', value: 'a' }, { label: 'B', value: 'b', is_default: true }] })
    expect(defaultAnswer(q)).toBe('b')
  })

  it('auto-selects a single option even without is_default', () => {
    expect(defaultAnswer(fixed({ options: [{ label: 'Only', value: 'only' }] }))).toBe('only')
  })

  it('is null with multiple options and no default', () => {
    expect(defaultAnswer(fixed())).toBeNull()
  })
})

describe('visibleQuestions', () => {
  const parent = fixed({ question_key: 'parent' })
  const child = fixed({ question_key: 'child', depends_on_question: 'parent', depends_on_option: 'yes' })

  it('always shows a question with no dependency', () => {
    expect(visibleQuestions([parent], {}).map((q) => q.question_key)).toEqual(['parent'])
  })

  it('hides a follow-up until its parent is answered the matching way', () => {
    expect(visibleQuestions([parent, child], {}).map((q) => q.question_key)).toEqual(['parent'])
    expect(visibleQuestions([parent, child], { parent: 'no' }).map((q) => q.question_key)).toEqual(['parent'])
    expect(visibleQuestions([parent, child], { parent: 'yes' }).map((q) => q.question_key)).toEqual([
      'parent',
      'child',
    ])
  })

  it('follows a default answer for visibility when nothing was explicitly chosen', () => {
    const autoYesParent = fixed({
      question_key: 'parent',
      options: [{ label: 'Yes', value: 'yes', is_default: true }, { label: 'No', value: 'no' }],
    })
    expect(visibleQuestions([autoYesParent, child], {}).map((q) => q.question_key)).toEqual(['parent', 'child'])
  })

  it('hides a grandchild whose own parent is hidden', () => {
    const grandchild = fixed({
      question_key: 'grandchild',
      depends_on_question: 'child',
      depends_on_option: 'yes',
    })
    expect(visibleQuestions([parent, child, grandchild], {}).map((q) => q.question_key)).toEqual(['parent'])
    expect(
      visibleQuestions([parent, child, grandchild], { parent: 'yes', child: 'yes' }).map((q) => q.question_key),
    ).toEqual(['parent', 'child', 'grandchild'])
  })
})

describe('reviewRows', () => {
  it('shows the label of the chosen Fixed answer', () => {
    const rows = reviewRows([fixed()], { q1: 'yes' })
    expect(rows).toEqual([
      { question_key: 'q1', label: 'Question?', answer: 'Yes', was_fallback: false, auto_answered: false, can_override: false, overridden: false },
    ])
  })

  it('flags an auto-answered (default) question', () => {
    const q = fixed({ options: [{ label: 'Only', value: 'only' }] })
    const rows = reviewRows([q], {})
    expect(rows[0]).toMatchObject({ answer: 'Only', auto_answered: true })
  })

  it('shows a Dynamic answer by its resolved label', () => {
    const q = { question_key: 'sp', label: 'Sales person?', question_type: 'Dynamic', options: [{ label: 'Jane Doe', value: 'HR-SP-0001' }], can_override: false }
    const rows = reviewRows([q], { sp: 'HR-SP-0001' })
    expect(rows[0].answer).toBe('Jane Doe')
  })

  it('shows an override only when the question allows it', () => {
    const overridable = fixed({ can_override: true })
    const rows = reviewRows([overridable], { q1: 'yes' }, { q1: 'Overseas' })
    expect(rows[0]).toMatchObject({ answer: 'Overseas', overridden: true })

    const notOverridable = fixed({ can_override: false })
    const rows2 = reviewRows([notOverridable], { q1: 'yes' }, { q1: 'Overseas' })
    expect(rows2[0]).toMatchObject({ answer: 'Yes', overridden: false })
  })

  it('omits questions hidden by branching', () => {
    const parent = fixed({ question_key: 'parent' })
    const child = fixed({ question_key: 'child', depends_on_question: 'parent', depends_on_option: 'yes' })
    const rows = reviewRows([parent, child], { parent: 'no' })
    expect(rows.map((r) => r.question_key)).toEqual(['parent'])
  })
})

describe('branching operator and mandatory flag', () => {
  const country = fixed({
    question_key: 'country',
    options: [
      { label: 'India', value: 'india' },
      { label: 'United States', value: 'usa' },
    ],
    is_mandatory: true,
  })
  const overseas = fixed({
    question_key: 'overseas',
    depends_on_question: 'country',
    depends_on_option: 'india',
    depends_on_operator: 'Is not',
  })

  it('shows an "Is not" follow-up for every parent answer except the named one', () => {
    expect(visibleQuestions([country, overseas], { country: 'usa' }).map((q) => q.question_key)).toContain('overseas')
    expect(visibleQuestions([country, overseas], { country: 'india' }).map((q) => q.question_key)).not.toContain('overseas')
    expect(visibleQuestions([country, overseas], {}).map((q) => q.question_key)).not.toContain('overseas')
  })

  it('flags the fallback in review rows when nothing was answered', () => {
    const withFallback = fixed({ question_key: 'gst', fallback_value: 'Unregistered' })
    const rows = reviewRows([withFallback], {})
    expect(rows[0]).toMatchObject({ answer: 'Default', was_fallback: true })
  })

  it('lists visible mandatory questions that nothing satisfies', () => {
    expect(unansweredMandatory([country, overseas], {})).toEqual([country])
    expect(unansweredMandatory([country, overseas], { country: 'india' })).toEqual([])
    const withFallback = fixed({ question_key: 'cur', is_mandatory: true, fallback_value: 'INR' })
    expect(unansweredMandatory([withFallback], {})).toEqual([])
  })
})

describe('resolvedFields (review values)', () => {
  const question = (key, extra = {}) => ({
    question_key: key,
    label: `Q ${key}`,
    target_doctype: 'Customer',
    target_fieldname: key,
    target_label: `Label ${key}`,
    target_fieldtype: 'Data',
    target_field_options: null,
    question_type: 'Fixed',
    depends_on_question: null,
    depends_on_option: null,
    depends_on_operator: 'Is',
    fallback_value: null,
    can_override: false,
    options: [],
    ...extra,
  })

  it('resolves one row per field with the mapped value, not the answer', () => {
    const group = question('customer_group', {
      target_fieldtype: 'Link',
      target_field_options: 'Customer Group',
      options: [
        { label: 'Business', value: 'business', mapped_value: 'Commercial' },
        { label: 'Government', value: 'government', mapped_value: 'Government' },
      ],
    })
    const { rows } = resolvedFields([group], { customer_group: 'business' })
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({
      label: 'Label customer_group',
      fieldtype: 'Link',
      field_options: 'Customer Group',
      value: 'Commercial',
      overridden: false,
      can_override: false,
    })
  })

  it('applies the overlay: a later question on the same field wins only when it resolves a value', () => {
    const first = question('gst_registered', {
      target_fieldname: 'gst_category',
      fallback_value: 'Unregistered',
      options: [
        { label: 'Yes', value: 'yes' },
        { label: 'No', value: 'no', mapped_value: 'Unregistered' },
      ],
    })
    const later = question('gst_type', {
      target_fieldname: 'gst_category',
      sequence: 2,
      options: [
        { label: 'Regular', value: 'regular', mapped_value: 'Registered Regular' },
        { label: 'Composition', value: 'composition', mapped_value: 'Registered Composition' },
      ],
    })
    let { rows } = resolvedFields([first, later], {})
    expect(rows[0]).toMatchObject({ value: 'Unregistered', was_fallback: true })
    ;({ rows } = resolvedFields([first, later], { gst_type: 'regular' }))
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ value: 'Registered Regular', was_fallback: false })
  })

  it('shows an overridden value only when the question allows it', () => {
    const q = question('territory', { can_override: true, options: [{ label: 'India', value: 'in', mapped_value: 'India' }] })
    expect(resolvedFields([q], { territory: 'in' }, { territory: 'Custom' }).rows[0]).toMatchObject({
      value: 'Custom',
      overridden: true,
    })
    const locked = question('currency', { options: [{ label: 'INR', value: 'inr', mapped_value: 'INR' }] })
    expect(resolvedFields([locked], { currency: 'inr' }, { currency: 'USD' }).rows[0]).toMatchObject({
      value: 'INR',
      overridden: false,
    })
  })

  it('collects Sales Team questions into sales_persons instead of a field row', () => {
    const sp = question('sales_person', {
      target_fieldname: 'sales_team',
      question_type: 'Dynamic',
      options: [{ label: 'Jane Doe', value: 'SP-0001' }],
    })
    const { rows, sales_persons } = resolvedFields([sp], { sales_person: 'SP-0001' })
    expect(rows).toHaveLength(0)
    expect(sales_persons).toEqual([{ value: 'SP-0001', overridden: false, question_key: 'sales_person' }])
  })

  it('never resolves a value from a question hidden by branching', () => {
    const parent = question('location', {
      options: [
        { label: 'India', value: 'india', mapped_value: 'India' },
        { label: 'Elsewhere', value: 'elsewhere', mapped_value: 'Rest Of The World' },
      ],
    })
    const child = question('gst', {
      target_fieldname: 'gst_category',
      depends_on_question: 'location',
      depends_on_option: 'india',
      options: [{ label: 'No', value: 'no', mapped_value: 'Unregistered' }],
    })
    expect(resolvedFields([parent, child], { location: 'elsewhere', gst: 'no' }).rows).toEqual([
      expect.objectContaining({ key: 'Customer.location', value: 'Rest Of The World' }),
    ])
  })
})

describe('descendantKeys', () => {
  const gate = fixed({ question_key: 'gst_registered' })
  const child = fixed({ question_key: 'gst_registration_type', depends_on_question: 'gst_registered' })
  const grandchild = fixed({ question_key: 'gst_sez', depends_on_question: 'gst_registration_type' })
  const unrelated = fixed({ question_key: 'customer_type' })

  it('finds direct and nested descendants of the root key', () => {
    expect(descendantKeys([gate, child, grandchild, unrelated], 'gst_registered')).toEqual(
      new Set(['gst_registration_type', 'gst_sez']),
    )
  })

  it('excludes the root key itself and unrelated questions', () => {
    const keys = descendantKeys([gate, child, grandchild, unrelated], 'gst_registered')
    expect(keys.has('gst_registered')).toBe(false)
    expect(keys.has('customer_type')).toBe(false)
  })

  it('is empty when nothing depends on the root key', () => {
    expect(descendantKeys([unrelated], 'gst_registered')).toEqual(new Set())
  })

  it('is empty for an empty or missing question list', () => {
    expect(descendantKeys([], 'gst_registered')).toEqual(new Set())
    expect(descendantKeys(undefined, 'gst_registered')).toEqual(new Set())
  })
})
