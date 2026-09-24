import { watch } from 'vue'
import { api } from '@/lib/api'
import { debounce } from '@/lib/debounce'

/**
 * Keeps a Dynamic question's options live as earlier answers change — e.g. a
 * Sales Person question filtered by Territory should only start offering
 * choices once Territory is actually answered. Calls
 * `pranera_crm.erpnext_customer.refresh_questions` (debounced) whenever
 * `answers` changes and patches the returned options back into `questions` (a
 * ref/reactive array, matched by `question_key`) in place, so QuestionField's
 * own rendering picks them up through normal reactivity — nothing else needs
 * to change.
 *
 * A no-op (never calls the endpoint) unless `questions` has at least one
 * Dynamic question and `enabled` is true — `refresh_questions` itself requires
 * the ERPNext bridge to be on, same as the rest of this section.
 */
export function useDynamicOptionsRefresh(scope, questions, answers, enabled) {
  const hasDynamicQuestions = () => (questions.value || []).some((q) => q.question_type === 'Dynamic')

  const refresh = debounce(async () => {
    if (!enabled.value || !hasDynamicQuestions()) return
    let fresh
    try {
      fresh = await api('pranera_crm.erpnext_customer.refresh_questions', {
        scope,
        answers: { ...answers },
      })
    } catch {
      return
    }
    const optionsByKey = Object.fromEntries(fresh.map((q) => [q.question_key, q.options]))
    for (const q of questions.value || []) {
      if (q.question_key in optionsByKey) q.options = optionsByKey[q.question_key]
    }
  }, 400)

  watch(
    () => JSON.stringify(answers),
    (value, old) => {
      if (old !== undefined) refresh()
    },
  )
}
