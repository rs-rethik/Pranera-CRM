import { createStore, del, entries, get, set } from 'idb-keyval'

// Drafts are kept per user so a shared device never shows one person's lead
// data to another. They live only on this device (IndexedDB, with a
// localStorage fallback when IndexedDB is unavailable, e.g. some private modes).

const VERSION = 1
const MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000
const LS_PREFIX = 'pranera:draft:'

let store = null
function idb() {
  if (store === null) {
    try {
      store = createStore('pranera-crm', 'drafts')
    } catch {
      store = false
    }
  }
  return store || null
}

const keyFor = (user, lead) => `${user}::${lead}`

export async function saveDraft(user, lead, data) {
  const record = { ...data, v: VERSION, user, lead, savedAt: Date.now() }
  try {
    if (idb()) return await set(keyFor(user, lead), record, idb())
  } catch {
    /* fall through to localStorage */
  }
  try {
    localStorage.setItem(LS_PREFIX + keyFor(user, lead), JSON.stringify(record))
  } catch {
    /* storage unavailable: the draft just isn't persisted */
  }
}

export async function loadDraft(user, lead) {
  let record = null
  try {
    if (idb()) record = await get(keyFor(user, lead), idb())
  } catch {
    /* ignore */
  }
  if (!record) {
    try {
      record = JSON.parse(localStorage.getItem(LS_PREFIX + keyFor(user, lead)) || 'null')
    } catch {
      record = null
    }
  }
  if (!record || record.v !== VERSION) return null
  if (Date.now() - record.savedAt > MAX_AGE_MS) {
    await clearDraft(user, lead)
    return null
  }
  return record
}

export async function clearDraft(user, lead) {
  try {
    if (idb()) await del(keyFor(user, lead), idb())
  } catch {
    /* ignore */
  }
  try {
    localStorage.removeItem(LS_PREFIX + keyFor(user, lead))
  } catch {
    /* ignore */
  }
}

/** Drafts for this user, newest first (also prunes expired ones). */
export async function listDrafts(user) {
  const found = new Map()
  try {
    if (idb()) {
      for (const [, record] of await entries(idb())) found.set(record.lead + record.user, record)
    }
  } catch {
    /* ignore */
  }
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key?.startsWith(LS_PREFIX)) continue
      const record = JSON.parse(localStorage.getItem(key) || 'null')
      if (record) found.set(record.lead + record.user, record)
    }
  } catch {
    /* ignore */
  }

  const live = []
  for (const record of found.values()) {
    if (record.v !== VERSION || record.user !== user) continue
    if (Date.now() - record.savedAt > MAX_AGE_MS) {
      clearDraft(record.user, record.lead)
      continue
    }
    live.push(record)
  }
  return live.sort((a, b) => b.savedAt - a.savedAt)
}
