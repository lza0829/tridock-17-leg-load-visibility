import { ref, computed } from 'vue'
import { api } from './api'

const holds = ref([])
let loaded = false

async function refreshHolds() {
  try {
    holds.value = await api('/holds?active_only=true')
    loaded = true
  } catch {
    // Backend remains the enforcement point; a failed fetch must not block the UI.
    holds.value = []
  }
}

export function useHolds() {
  const heldCodes = computed(() => new Set(holds.value.map(h => h.supplier_code)))
  const isHeld = code => heldCodes.value.has((code || '').trim())
  if (!loaded) refreshHolds()
  return { holds, heldCodes, isHeld, refreshHolds }
}
