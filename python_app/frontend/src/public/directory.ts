export interface DirectoryData {
  kind: 'actors' | 'countries' | 'categories'
  title: string
  eyebrow: string
  description: string
  items: { name: string; count: number; href: string }[]
  query: string
  count: number
  url: string
  catalogUrl: string
  addActorUrl?: string | null
  pagination?: { page: number; pages: number; previous: string | null; next: string | null }
}
