import type { CatalogValues } from './types'

// The Django header stays mounted so its disclosure menus keep keyboard and focus behavior.
export function syncCatalogHeader(values: CatalogValues, catalogPath: string) {
  const header = document.querySelector('.site-header')
  if (!header) return
  const search = header.querySelector<HTMLInputElement>('.header-search input[name=q]')
  if (search) search.value = values.q

  const filtered = values.category || values.country || values.actor
  const current = {
    home: !filtered && !values.kind,
    movie: !filtered && values.kind === 'movie',
    series: !filtered && values.kind === 'series',
    genre: Boolean(values.category && !values.country && !values.actor),
    country: Boolean(values.country && !values.actor),
    actor: Boolean(values.actor),
  }

  const mark = (selector: string, active: boolean) => {
    const link = header.querySelector(selector)
    if (active) link?.setAttribute('aria-current', 'page')
    else link?.removeAttribute('aria-current')
  }

  mark('.main-nav > a[href="' + catalogPath + '"]', current.home)
  mark('.main-nav > a[href="' + catalogPath + '?kind=movie"]', current.movie)
  mark('.main-nav > a[href="' + catalogPath + '?kind=series"]', current.series)
  mark('.main-nav > a[href="/actors/"]', current.actor)
  const filters = new URLSearchParams(Object.entries(values).filter(([, value]) => value))
  for (const [menu, field] of [['genre', 'category'], ['country', 'country']] as const) {
    mark(`[data-nav-fallback="${menu}"]`, current[menu])
    header.querySelector(`[data-nav-key="${menu}"]`)?.classList.toggle('is-current', current[menu])
    for (const link of header.querySelectorAll<HTMLAnchorElement>(`[data-nav-panel="${menu}"] .genre-dropdown-links a`)) {
      const choice = new URL(link.href).searchParams.get(field)
      if (!choice) continue
      const query = new URLSearchParams(filters)
      query.set(field, choice)
      link.href = `${catalogPath}?${query}`
      if (choice === values[field]) link.setAttribute('aria-current', 'page')
      else link.removeAttribute('aria-current')
    }
  }
}
