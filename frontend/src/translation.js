// Same contract as Frappe CRM's translation plugin: messages come from the boot
// data (`translated_messages`, i.e. the site/user language, merged from every
// app's translations and the Translation doctype) and unknown strings fall back
// to English. Kept free of frappe-ui imports so it also works in unit tests.

let messages = {}

export function setTranslations(translated) {
  messages = translated || {}
}

export function getTranslations() {
  return messages
}

function format(message, replace) {
  return message.replace(/{(\d+)}/g, (match, number) =>
    typeof replace[number] !== 'undefined' ? replace[number] : match,
  )
}

export function __(message, replace = [], context = null) {
  let translated = ''

  if (context) {
    const key = `${message}:${context}`
    if (messages[key]) translated = messages[key]
  }
  if (!translated) translated = messages[message] || message

  return /{\d+}/.test(message) ? format(translated, replace || []) : translated
}

export default function translationPlugin(app) {
  app.config.globalProperties.__ = __
  window.__ = __
}
