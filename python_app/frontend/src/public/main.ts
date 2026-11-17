import { createApp } from 'vue'
import { mountShelves } from '../home/shelves'
import { AvatarController } from './avatar'
import CharacterCount from './CharacterCount.vue'
import { bindCheckoutSubmission } from './checkout'
import Directory from './Directory.vue'
import type { DirectoryData } from './directory'
import MembershipPlans from './MembershipPlans.vue'
import MovieRating from './MovieRating.vue'
import PasswordToggle from './PasswordToggle.vue'

function mountDirectory() {
  const root = document.querySelector<HTMLElement>('[data-vue-directory]')
  const fallback = document.querySelector<HTMLElement>('[data-directory-fallback]')
  const state = document.querySelector('#vue-directory-data')
  if (!root || !fallback || !state?.textContent) return
  const initial: DirectoryData = JSON.parse(state.textContent)
  const app = createApp(Directory, { initial })
  app.mount(root)
  if (root.querySelector('h1')) {
    root.hidden = false
    fallback.remove()
    root.dataset.vueDirectory = 'mounted'
  } else app.unmount()
}

function mountMembership() {
  const form = document.querySelector<HTMLFormElement>('#membership-form')
  if (!form) return
  bindCheckoutSubmission(form)
  const root = form.querySelector<HTMLElement>('[data-vue-plan-controls]')
  if (!root) return
  const radios = [...form.querySelectorAll<HTMLInputElement>('input[name="plan"]')]
  const plans = radios.map(radio => ({
    id: radio.value,
    name: radio.parentElement?.querySelector('strong')?.textContent?.trim() || '',
    duration: radio.parentElement?.querySelector('small')?.textContent?.trim() || '',
    price: radio.dataset.price || '',
  }))
  const selected = radios.find(radio => radio.checked)?.value || plans[0]?.id
  if (!selected || plans.some(plan => !plan.id || !plan.name || !plan.price)) return

  const fallback = [...root.childNodes]
  const app = createApp(MembershipPlans, { plans, selected })
  app.mount(root)
  if (!root.querySelector('input[name="plan"]')) {
    app.unmount()
    root.replaceChildren(...fallback)
    return
  }
  form.dataset.vueMembership = 'true'
}

function mountAvatar() {
  const form = document.querySelector<HTMLFormElement>('[data-avatar-editor]')
  if (!form) return
  const file = form.querySelector<HTMLInputElement>('[data-avatar-file]')
  const image = form.querySelector<HTMLImageElement>('[data-avatar-preview-image]')
  const status = form.querySelector<HTMLElement>('[data-avatar-status]')
  const reset = form.querySelector<HTMLButtonElement>('[data-avatar-reset]')
  const remove = form.querySelector<HTMLInputElement>('[data-avatar-remove]')
  const saved = form.querySelector<HTMLElement>('[data-avatar-preview]')?.dataset.avatarCurrent || ''
  if (!file || !image || !status || !reset) return
  const root = document.createElement('span')
  root.hidden = true
  form.append(root)
  createApp(AvatarController, { editor: { file, image, status, reset, remove, saved } }).mount(root)
  form.dataset.vueAvatar = 'mounted'
}

function mountMovieRating() {
  const form = document.querySelector<HTMLFormElement>('[data-vue-rating]')
  const field = form?.querySelector<HTMLSelectElement>('[name="score"]')
  const label = field?.closest('label')
  const submit = form?.querySelector<HTMLButtonElement>('button')
  if (!form || !field || !label || !submit) return
  const root = document.createElement('span')
  root.className = 'public-control-mount'
  const options = [...field.options].map(option => ({
    value: option.value,
    label: option.label,
    disabled: option.disabled,
  }))
  const app = createApp(MovieRating, { options, current: field.value })
  app.mount(root)
  if (root.querySelector('select')) {
    label.replaceWith(root)
    submit.remove()
    form.dataset.vueRating = 'mounted'
  } else app.unmount()
}

function mountFieldControls() {
  for (const field of document.querySelectorAll<HTMLInputElement>('[data-vue-passwords] input[type=password][id]')) {
    const root = document.createElement('span')
    field.after(root)
    createApp(PasswordToggle, { field }).mount(root)
  }
  for (const field of document.querySelectorAll<HTMLTextAreaElement>('textarea[data-vue-count][maxlength]')) {
    if (field.maxLength <= 0) continue
    const root = document.createElement('span')
    field.after(root)
    createApp(CharacterCount, { field }).mount(root)
  }
}

for (const enhance of [mountDirectory, mountMembership, mountAvatar, mountMovieRating, mountFieldControls]) {
  try {
    enhance()
  } catch (error) {
    console.error('Lumière public controls could not start', error)
  }
}
const library = document.querySelector('.library-page')
if (library) mountShelves(library)
