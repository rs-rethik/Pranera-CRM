<template>
  <FrappeUIProvider>
    <router-view />
  </FrappeUIProvider>
</template>

<script setup>
import { FrappeUIProvider, setConfig, useTheme } from 'frappe-ui'
import { getSite } from '@/lib/site'
import { getTranslations } from '@/translation'

// Theme: same as CRM. frappe-ui keeps the choice in localStorage ("theme" =
// light | dark | system) and applies it as <html data-theme>. Both apps live on
// the same origin, so the wizard picks up whatever the user chose in CRM.
const { setTheme } = useTheme()
if (!localStorage.getItem('theme')) {
  setTheme('light')
}

// Same frappe-ui configuration as CRM's App.vue: time zones and translations.
const site = getSite()
setConfig('systemTimezone', site.timezone?.system || null)
setConfig('localTimezone', site.timezone?.user || null)
setConfig('translatedMessages', getTranslations())
</script>
