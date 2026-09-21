import { onMounted, onUnmounted, ref } from 'vue'

/** Reactive navigator.onLine. */
export function useOnline() {
  const online = ref(navigator.onLine)
  const goOnline = () => (online.value = true)
  const goOffline = () => (online.value = false)

  onMounted(() => {
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
  })
  onUnmounted(() => {
    window.removeEventListener('online', goOnline)
    window.removeEventListener('offline', goOffline)
  })

  return online
}
