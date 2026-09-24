<template>
  <FrappeUIProvider>
    <router-view />
  </FrappeUIProvider>
</template>

<script setup>
import { FrappeUIProvider, setConfig, useTheme } from 'frappe-ui'
import { getSite } from '@/lib/site'
import { getTranslations } from '@/translation'

const { setTheme } = useTheme()
if (!localStorage.getItem('theme')) {
  setTheme('light')
}

const site = getSite()
setConfig('systemTimezone', site.timezone?.system || null)
setConfig('localTimezone', site.timezone?.user || null)
setConfig('translatedMessages', getTranslations())
</script>
