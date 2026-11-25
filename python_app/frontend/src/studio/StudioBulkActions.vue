<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

interface ActionOption {value: string; label: string}
const { form, legacy, action, submit, options } = defineProps<{
  form: HTMLFormElement
  legacy: HTMLElement
  action: HTMLSelectElement
  submit: HTMLButtonElement
  options: ActionOption[]
}>()
const selected = ref(0)
const across = ref(false)
const busy = ref(false)
const acrossLabel = ref('')
const acrossQuestion = ref('')
const acrossClear = ref('')
const selectedAction = ref('')
const listeners = new AbortController()
let observer: MutationObserver | undefined
let disposed = false

const canDelete = options.some(option => option.value === 'delete_selected')
const otherActions = options.filter(option => option.value !== 'delete_selected')
const disabled = computed(() => busy.value || (!across.value && selected.value === 0))

function refresh() {
  if (disposed) return
  selected.value = form.querySelectorAll('input.action-select:checked').length
  across.value = legacy.querySelector<HTMLInputElement>('input.select-across')?.value === '1'
  acrossLabel.value = legacy.querySelector('.all')?.textContent?.trim() || 'Đã chọn tất cả kết quả'
  const question = legacy.querySelector<HTMLElement>('.question')
  const clear = legacy.querySelector<HTMLElement>('.clear')
  acrossQuestion.value = question && !question.classList.contains('hidden') ? question.textContent?.trim() || '' : ''
  acrossClear.value = clear && !clear.classList.contains('hidden') ? clear.textContent?.trim() || 'Bỏ chọn' : ''
}

function afterNativeActions() { queueMicrotask(refresh) }

function run(value: string) {
  refresh()
  if (disabled.value || !options.some(option => option.value === value)) return
  action.value = value
  action.dispatchEvent(new Event('change', {bubbles: true}))
  // Click the original submitter to retain Django's unsaved-row-edit guard,
  // native validation, CSRF fields and server-side action confirmation.
  submit.click()
}

function selectAcross() {
  legacy.querySelector<HTMLAnchorElement>('.question a')?.click()
  refresh()
}

function clearAcross() {
  legacy.querySelector<HTMLAnchorElement>('.clear a')?.click()
  refresh()
}

onMounted(() => {
  const {signal} = listeners
  form.addEventListener('change', afterNativeActions, {signal})
  form.addEventListener('click', afterNativeActions, {signal})
  form.addEventListener('reset', afterNativeActions, {signal})
  form.addEventListener('submit', event => {
    queueMicrotask(() => {if (!disposed && !event.defaultPrevented) busy.value = true})
  }, {signal})
  window.addEventListener('pageshow', () => {busy.value = false; afterNativeActions()}, {signal})
  observer = new MutationObserver(refresh)
  observer.observe(legacy, {subtree: true, attributes: true, childList: true, characterData: true})
  refresh()
})
onUnmounted(() => {disposed = true; listeners.abort(); observer?.disconnect()})
</script>

<template>
  <div class="studio-bulk-actions" :aria-busy="busy">
    <div class="studio-bulk-selection" id="studio-bulk-selection-status" role="status" aria-live="polite">
      <svg class="studio-bulk-check" viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="4"/><path d="m8 12 3 3 5-6"/></svg>
      <span v-if="across">{{ acrossLabel }}</span>
      <span v-else-if="selected"><strong>{{ selected }}</strong> mục đã chọn</span>
      <span v-else>Chọn các mục để thao tác</span>
    </div>
    <div class="studio-bulk-buttons">
      <button v-if="canDelete" type="button" class="studio-bulk-delete" :disabled="disabled" aria-describedby="studio-bulk-selection-status" @click="run('delete_selected')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v5m4-5v5"/></svg>
        Xóa đã chọn <span v-if="selected && !across">({{ selected }})</span>
      </button>
      <template v-if="otherActions.length <= 2">
        <button v-for="option in otherActions" :key="option.value" type="button" class="studio-bulk-action" :disabled="disabled" @click="run(option.value)">{{ option.label }}</button>
      </template>
      <div v-else class="studio-bulk-more">
        <label class="sr-only" for="studio-bulk-action-choice">Thao tác khác</label>
        <select id="studio-bulk-action-choice" v-model="selectedAction" :disabled="disabled"><option value="">Thao tác khác</option><option v-for="option in otherActions" :key="option.value" :value="option.value">{{ option.label }}</option></select>
        <button type="button" class="studio-bulk-action" :disabled="disabled || !selectedAction" @click="run(selectedAction)">Thực hiện</button>
      </div>
    </div>
    <div v-if="acrossQuestion || acrossClear" class="studio-bulk-across">
      <button v-if="acrossQuestion && !across" type="button" :disabled="busy" @click="selectAcross">{{ acrossQuestion }}</button>
      <button v-if="acrossClear && across" type="button" :disabled="busy" @click="clearAcross">{{ acrossClear }}</button>
    </div>
  </div>
</template>
