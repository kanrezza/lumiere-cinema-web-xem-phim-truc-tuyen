import { defineComponent, h, onMounted, onUnmounted, ref, watchEffect } from 'vue'
import type { PropType } from 'vue'

interface AvatarEditor {
  file: HTMLInputElement
  remove: HTMLInputElement | null
  image: HTMLImageElement
  status: HTMLElement
  reset: HTMLButtonElement
  saved: string
}

const imageTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])

export const AvatarController = defineComponent({
  props: { editor: { type: Object as PropType<AvatarEditor>, required: true } },
  setup({ editor }) {
    const { file, remove, image, status, reset, saved } = editor
    const initialStatus = status.textContent || ''
    const initialInvalid = file.getAttribute('aria-invalid')
    const preview = ref(remove?.checked ? '' : saved)
    const message = ref(initialStatus)
    const changed = ref(Boolean(remove?.checked))
    const error = ref(false)
    let reader: FileReader | undefined

    function cancelRead() {
      const canceled = reader
      reader = undefined
      if (canceled?.readyState === FileReader.LOADING) canceled.abort()
    }

    function restoreSaved() {
      cancelRead()
      file.value = ''
      if (remove) remove.checked = false
      preview.value = saved
      message.value = initialStatus
      changed.value = false
      error.value = false
    }

    function rejectFile(text: string) {
      file.value = ''
      preview.value = saved
      message.value = text
      error.value = true
    }

    function chooseImage() {
      cancelRead()
      const chosen = file.files?.[0]
      if (!chosen) {
        restoreSaved()
        return
      }
      if (remove) remove.checked = false
      changed.value = true
      error.value = false
      preview.value = saved
      if (chosen.size > 5 * 1024 * 1024) {
        rejectFile('Ảnh vượt quá 5 MB. Vui lòng chọn ảnh nhỏ hơn.')
        return
      }
      if (chosen.type && !imageTypes.has(chosen.type)) {
        rejectFile('Vui lòng chọn ảnh JPG, PNG hoặc WebP.')
        return
      }
      message.value = 'Đang tạo ảnh xem trước…'
      const current = new FileReader()
      reader = current
      current.addEventListener('load', () => {
        if (reader !== current || typeof current.result !== 'string') return
        preview.value = current.result
        message.value = 'Đang xem trước ảnh mới. Bấm “Lưu ảnh” để cập nhật ở cả hai vị trí.'
      })
      current.addEventListener('error', () => {
        if (reader === current) rejectFile('Không đọc được ảnh. Vui lòng chọn lại tệp khác.')
      })
      current.readAsDataURL(chosen)
    }

    function removeImage() {
      restoreSaved()
      if (remove) remove.checked = true
      preview.value = ''
      changed.value = true
      message.value = 'Sẽ dùng lại chữ cái mặc định sau khi bạn bấm “Lưu ảnh”.'
    }

    function toggleRemoval() {
      if (remove?.checked) removeImage()
      else restoreSaved()
    }

    function imageFailed() {
      // A stale load error must not replace a newer preview.
      if (image.getAttribute('src') !== preview.value) return
      if (preview.value.startsWith('data:')) {
        rejectFile('Không thể xem trước ảnh này. Vui lòng chọn ảnh JPG, PNG hoặc WebP hợp lệ.')
      } else {
        preview.value = ''
      }
    }

    function resetSelection() {
      restoreSaved()
      file.focus()
    }

    watchEffect(() => {
      image.hidden = !preview.value
      if (preview.value) {
        if (image.getAttribute('src') !== preview.value) image.src = preview.value
      } else image.removeAttribute('src')
      status.textContent = message.value
      status.classList.toggle('is-error', error.value)
      reset.hidden = !changed.value
      if (error.value) file.setAttribute('aria-invalid', 'true')
      else if (changed.value || initialInvalid === null) file.removeAttribute('aria-invalid')
      else file.setAttribute('aria-invalid', initialInvalid)
    })

    onMounted(() => {
      if (saved && image.complete && !image.naturalWidth) imageFailed()
      file.addEventListener('change', chooseImage)
      remove?.addEventListener('change', toggleRemoval)
      reset.addEventListener('click', resetSelection)
      image.addEventListener('error', imageFailed)
    })
    onUnmounted(() => {
      cancelRead()
      file.removeEventListener('change', chooseImage)
      remove?.removeEventListener('change', toggleRemoval)
      reset.removeEventListener('click', resetSelection)
      image.removeEventListener('error', imageFailed)
    })
    return () => h('span', { hidden: true })
  },
})
