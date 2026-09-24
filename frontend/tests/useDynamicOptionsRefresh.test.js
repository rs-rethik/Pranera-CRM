import { computed, reactive } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useDynamicOptionsRefresh } from '@/composables/useDynamicOptionsRefresh'

vi.mock('@/lib/api', () => ({ api: vi.fn() }))
const { api } = await import('@/lib/api')

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

describe('useDynamicOptionsRefresh', () => {
  it('re-fetches and patches options in place once a watched answer changes', async () => {
    const questions = reactive([
      { question_key: 'territory', question_type: 'Fixed', options: [] },
      { question_key: 'sales_person', question_type: 'Dynamic', options: [{ label: 'Stale', value: 'SP-OLD' }] },
    ])
    const answers = reactive({ territory: 'tamil_nadu' })
    api.mockResolvedValue([{ question_key: 'sales_person', options: [{ label: 'Fresh', value: 'SP-NEW' }] }])

    useDynamicOptionsRefresh(
      'Organization',
      computed(() => questions),
      answers,
      computed(() => true),
    )

    answers.territory = 'other_india'
    await wait(450)

    expect(api).toHaveBeenCalledWith('pranera_crm.erpnext_customer.refresh_questions', {
      scope: 'Organization',
      answers: { territory: 'other_india' },
    })
    expect(questions[1].options).toEqual([{ label: 'Fresh', value: 'SP-NEW' }])
    expect(questions[0].options).toEqual([])
  })

  it('never calls the endpoint when there is no Dynamic question in scope', async () => {
    const questions = reactive([{ question_key: 'territory', question_type: 'Fixed', options: [] }])
    const answers = reactive({ territory: '' })
    api.mockClear()

    useDynamicOptionsRefresh(
      'Organization',
      computed(() => questions),
      answers,
      computed(() => true),
    )

    answers.territory = 'tamil_nadu'
    await wait(450)

    expect(api).not.toHaveBeenCalled()
  })

  it('never calls the endpoint when the ERPNext bridge is off', async () => {
    const questions = reactive([{ question_key: 'sales_person', question_type: 'Dynamic', options: [] }])
    const answers = reactive({ territory: '' })
    api.mockClear()

    useDynamicOptionsRefresh(
      'Organization',
      computed(() => questions),
      answers,
      computed(() => false),
    )

    answers.territory = 'tamil_nadu'
    await wait(450)

    expect(api).not.toHaveBeenCalled()
  })
})
