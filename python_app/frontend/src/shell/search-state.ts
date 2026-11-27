/** Abort old work and ignore stale replies even when a transport ignores abort. */
export type SearchMovie = { id: number; title: string; meta: string; url: string; poster: string | null; ready: boolean; vip: boolean }
export type SearchActor = { id: number; name: string; url: string }
export type SearchPayload = { query: string; movies: SearchMovie[]; actors: SearchActor[]; all_url: string }
export type SearchFetch = (url: string, init: RequestInit) => Promise<Pick<Response, 'ok' | 'redirected' | 'json'>>

export function searchableQuery(value: string) {
  return value.normalize('NFKD').replace(/\p{M}/gu, '').replace(/đ/gi, 'd').replace(/\s+/g, ' ').trim().length >= 2
}

export function moveSearchSelection(index: number, count: number, direction: 1 | -1): number {
  if (!count) return -1
  if (index < 0) return direction === 1 ? 0 : count - 1
  return (index + direction + count) % count
}

export function sameOriginSearchPath(value: unknown, origin: string): string | null {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return null
  try {
    const url = new URL(value, origin)
    return url.origin === origin ? url.pathname + url.search + url.hash : null
  } catch { return null }
}

function parsePayload(value: unknown, query: string, catalog: string, origin: string): SearchPayload {
  if (!value || typeof value !== 'object') throw new Error('Invalid search reply')
  const data = value as Partial<SearchPayload>
  if (!Array.isArray(data.movies) || !Array.isArray(data.actors)) throw new Error('Invalid search reply')
  const movies = data.movies.slice(0, 6).filter((item): item is SearchMovie => !!item && typeof item.title === 'string'
    && typeof item.meta === 'string' && typeof item.id === 'number' && !!sameOriginSearchPath(item.url, origin))
    .map(item => ({ ...item, url: sameOriginSearchPath(item.url, origin)!, poster: sameOriginSearchPath(item.poster, origin), ready: item.ready === true, vip: item.vip === true }))
  const actors = data.actors.slice(0, 3).filter((item): item is SearchActor => !!item && typeof item.name === 'string'
    && typeof item.id === 'number' && !!sameOriginSearchPath(item.url, origin))
    .map(item => ({ ...item, url: sameOriginSearchPath(item.url, origin)! }))
  const all = new URL(catalog, origin)
  all.searchParams.set('q', query)
  return { query, movies, actors, all_url: sameOriginSearchPath(data.all_url, origin) || all.pathname + all.search }
}

export class SearchSuggestionLoader {
  private version = 0
  private controller?: AbortController
  constructor(private endpoint: string, private catalog: string, private origin: string, private fetcher: SearchFetch) {}

  cancel() {
    this.version += 1
    this.controller?.abort()
    this.controller = undefined
  }

  async load(rawQuery: string): Promise<SearchPayload | null> {
    this.cancel()
    const query = rawQuery.trim().slice(0, 150)
    if (!searchableQuery(query)) return null
    const version = this.version
    const controller = new AbortController()
    this.controller = controller
    const endpoint = new URL(this.endpoint, this.origin)
    if (endpoint.origin !== this.origin) throw new Error('Search must stay on the current site')
    endpoint.searchParams.set('q', query)
    try {
      const response = await this.fetcher(endpoint.pathname + endpoint.search, { signal: controller.signal, credentials: 'same-origin' })
      if (version !== this.version) return null
      if (!response.ok || response.redirected) throw new Error('Search is unavailable')
      const body: unknown = await response.json()
      return version === this.version ? parsePayload(body, query, this.catalog, this.origin) : null
    } catch (error) {
      if (controller.signal.aborted || version !== this.version) return null
      throw error
    } finally {
      if (this.controller === controller) this.controller = undefined
    }
  }
}
