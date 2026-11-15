export interface CatalogValues {
  q: string
  category: string
  country: string
  year: string
  kind: string
  sort: string
  access: string
  actor: string
  availability: string
  release: string
  trailer: string
}

export interface FilterOption {
  value: string
  label: string
}

export interface CatalogData {
  title: string
  count: number
  values: CatalogValues
  categories: FilterOption[]
  countries: FilterOption[]
  years: number[]
  contentLinks: { href: string; label: string; active: boolean }[]
  activeFilters: string[]
  gridHtml: string
  pagination: { page: number; pages: number; previous: string | null; next: string | null }
}
