import { createApp } from 'vue'
import StudioNavigation from './StudioNavigation.vue'
import StudioPassword from './StudioPassword.vue'
import StudioSearch from './StudioSearch.vue'
import RecentVideoFilter from './RecentVideoFilter.vue'
import StudioBulkActions from './StudioBulkActions.vue'
import { mountTheme } from '../shell/theme'

function mountNavigation() {
  const mount = document.querySelector('[data-studio-vue-menu]')
  const fallback = document.querySelector('[data-studio-menu]')
  const sidebar = document.getElementById('studio-sidebar')
  const overlay = document.querySelector<HTMLButtonElement>('.studio-sidebar-overlay')
  if (!mount || !fallback || !sidebar) return

  const app = createApp(StudioNavigation, { sidebar, overlay })
  app.mount(mount)
  if (!mount.querySelector('[data-studio-menu]')) {
    app.unmount()
    return
  }
  fallback.remove()
  document.documentElement.setAttribute('data-studio-vue-navigation', '')
}

function mountSearch() {
  const mount = document.querySelector('[data-studio-vue-search]')
  const fallback = document.getElementById('changelist-search')
  const input = fallback?.querySelector<HTMLInputElement>('#searchbar')
  if (!mount || !fallback || !input) return

  const count = fallback.querySelector('.small.quiet')
  const clear = count?.querySelector<HTMLAnchorElement>('a')
  const app = createApp(StudioSearch, {
    inputName: input.name,
    initialQuery: input.value,
    placeholder: input.placeholder,
    label: fallback.querySelector('label')?.textContent?.trim() || 'Tìm kiếm',
    hiddenFields: [...fallback.querySelectorAll<HTMLInputElement>('input[type=hidden]')].map(
      field => ({ name: field.name, value: field.value }),
    ),
    help: fallback.querySelector('#searchbar_helptext')?.textContent?.trim() || '',
    resultCount: count?.firstChild?.textContent?.trim() || '',
    clearHref: clear?.getAttribute('href') || '',
    clearLabel: clear?.textContent?.trim() || '',
  })
  app.mount(mount)
  const search = mount.querySelector<HTMLInputElement>('#searchbar')
  if (!search) {
    app.unmount()
    return
  }
  const restoreFocus = document.activeElement === input
  fallback.remove()
  if (restoreFocus) search.focus({ preventScroll: true })
}

function mountVideoFilter() {
  const library = document.querySelector('[data-studio-video-library]')
  const mount = library?.querySelector('[data-studio-vue-video-filter]')
  if (!library || !mount) return

  const rows: { row: HTMLTableRowElement; status: string }[] = []
  const labels = new Map<string, string>()
  for (const row of library.querySelectorAll<HTMLTableRowElement>('[data-studio-video-status]')) {
    const status = row.dataset.studioVideoStatus
    const label = row.querySelector('.sd-status')?.textContent?.trim()
    if (!status || !label) continue
    rows.push({ row, status })
    labels.set(status, label)
  }
  if (labels.size < 2) return
  const options = Array.from(labels, ([value, label]) => ({ value, label }))
  createApp(RecentVideoFilter, { rows, options }).mount(mount)
}

function mountPasswordToggle() {
  const input = document.querySelector<HTMLInputElement>('#login-form input[type=password][id]')
  if (!input) return
  const mount = document.createElement('span')
  mount.className = 'studio-password-control'
  mount.dataset.studioPassword = ''
  input.after(mount)
  createApp(StudioPassword, { input }).mount(mount)
}

function mountBulkActions() {
  const form = document.querySelector<HTMLFormElement>('#changelist-form')
  const legacy = form?.querySelector<HTMLElement>('.actions')
  const action = legacy?.querySelector<HTMLSelectElement>('select[name=action]')
  const submit = legacy?.querySelector<HTMLButtonElement>('button[name=index]')
  if (!form || !legacy || !action || !submit) return
  const options = [...action.options].filter(option => option.value).map(option => ({value: option.value, label: option.textContent?.trim() || option.value}))
  if (!options.length) return
  const mount = document.createElement('div')
  mount.dataset.studioVueBulkActions = ''
  legacy.before(mount)
  const app = createApp(StudioBulkActions, {form, legacy, action, submit, options})
  app.mount(mount)
  if (!mount.querySelector('.studio-bulk-actions')) {
    app.unmount()
    mount.remove()
    return
  }
  for (const original of form.querySelectorAll<HTMLElement>('.actions')) original.hidden = true
}

mountNavigation()
mountTheme()
mountSearch()
mountVideoFilter()
mountPasswordToggle()
mountBulkActions()
