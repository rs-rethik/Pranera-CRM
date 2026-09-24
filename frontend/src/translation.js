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
