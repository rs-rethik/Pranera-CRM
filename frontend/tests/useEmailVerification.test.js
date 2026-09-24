import { nextTick, reactive } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useEmailVerification } from '@/composables/useEmailVerification'
import { validateStep } from '@/lib/validation'

vi.mock('@/lib/api', () => ({ api: vi.fn(), errorMessage: (e) => e.message }))
const { api } = await import('@/lib/api')

const newContact = (email = '') => reactive({
  mode: 'new',
  existing: '',
  values: { first_name: 'Ada', email },
  emailVerification: { verifiedEmail: '' },
})

describe('email verification', () => {
  it('blocks the step until the typed email is verified', () => {
    const form = { contact: newContact('ada@example.com'), customer: {} }
    expect(validateStep(1, form, {})).toHaveProperty('email')
    form.contact.emailVerification.verifiedEmail = 'ADA@example.com'
    expect(validateStep(1, form, {})).toEqual({})
  })

  it('does not require verification for an empty email or an existing contact', () => {
    expect(validateStep(1, { contact: newContact(''), customer: {} }, {})).toEqual({})
    const existing = newContact('ada@example.com')
    existing.mode = 'existing'
    existing.existing = 'CONTACT-1'
    expect(validateStep(1, { contact: existing, customer: {} }, {})).toEqual({})
  })

  it('sends a code, then verifies it', async () => {
    api.mockReset()
    api.mockResolvedValue({})
    const contact = newContact('ada@example.com')
    const v = useEmailVerification('LEAD-1', contact)

    expect(v.canVerify.value).toBe(true)
    await v.send()
    expect(api).toHaveBeenCalledWith('pranera_crm.email_verification.send_email_otp', { lead: 'LEAD-1', email: 'ada@example.com' })
    expect(v.codeSent.value).toBe(true)

    v.state.code = '123456'
    await v.confirm()
    expect(api).toHaveBeenLastCalledWith('pranera_crm.email_verification.verify_email_otp', {
      lead: 'LEAD-1',
      email: 'ada@example.com',
      otp: '123456',
    })
    expect(v.verified.value).toBe(true)
  })

  it('resets verification when the email changes', async () => {
    api.mockReset()
    api.mockResolvedValue({})
    const contact = newContact('ada@example.com')
    const v = useEmailVerification('LEAD-1', contact)
    await v.send()
    v.state.code = '123456'
    await v.confirm()
    expect(v.verified.value).toBe(true)

    contact.values.email = 'other@example.com'
    await nextTick()
    expect(v.verified.value).toBe(false)
    expect(contact.emailVerification.verifiedEmail).toBe('')
    expect(v.canVerify.value).toBe(true)
  })

  it('shows the server error and stays unverified on a wrong code', async () => {
    api.mockReset()
    api.mockResolvedValueOnce({})
    const v = useEmailVerification('LEAD-1', newContact('ada@example.com'))
    await v.send()
    api.mockRejectedValueOnce(new Error('Incorrect verification code'))
    v.state.code = '000000'
    await v.confirm()
    expect(v.verified.value).toBe(false)
    expect(v.state.error).toBe('Incorrect verification code')
  })
})
