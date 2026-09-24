import { computed, reactive, watch } from 'vue'
import { api, errorMessage } from '@/lib/api'
import { isValidEmail, normalizeEmail } from '@/lib/validation'

export function useEmailVerification(lead, contact) {
  const state = reactive({ codeSentTo: '', code: '', sending: false, confirming: false, error: '' })

  const email = computed(() => contact.values.email)
  const verified = computed(
    () => !!email.value && normalizeEmail(email.value) === normalizeEmail(contact.emailVerification.verifiedEmail),
  )
  const canVerify = computed(() => isValidEmail(email.value || '') && !verified.value)
  const codeSent = computed(() => !!state.codeSentTo && state.codeSentTo === normalizeEmail(email.value))

  watch(email, () => {
    state.error = ''
    if (!verified.value) contact.emailVerification.verifiedEmail = ''
    if (!codeSent.value) {
      state.codeSentTo = ''
      state.code = ''
    }
  })

  async function send() {
    if (state.sending || !canVerify.value) return
    state.sending = true
    state.error = ''
    try {
      await api('pranera_crm.email_verification.send_email_otp', { lead, email: email.value.trim() })
      state.codeSentTo = normalizeEmail(email.value)
      state.code = ''
    } catch (err) {
      state.error = errorMessage(err)
    } finally {
      state.sending = false
    }
  }

  async function confirm() {
    if (state.confirming || !state.code.trim() || !codeSent.value) return
    state.confirming = true
    state.error = ''
    try {
      await api('pranera_crm.email_verification.verify_email_otp', {
        lead,
        email: email.value.trim(),
        otp: state.code.trim(),
      })
      contact.emailVerification.verifiedEmail = email.value.trim()
      state.codeSentTo = ''
      state.code = ''
    } catch (err) {
      state.error = errorMessage(err)
    } finally {
      state.confirming = false
    }
  }

  return { state, verified, canVerify, codeSent, send, confirm }
}
