import { csrfToken } from '../shared/http'
import type { VoiceAction } from './voice-types'

export class VoiceRequestError extends Error {
  constructor(readonly status: number) {
    super('Không kết nối được với phòng thoại.')
  }
}

export async function voiceRequest<T>(url: string | URL, options: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 4500)
  try {
    const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options, signal: controller.signal})
    if (response.redirected || !response.ok) {
      throw new VoiceRequestError(response.redirected ? 403 : response.status)
    }
    return await response.json()
  } finally {
    window.clearTimeout(timeout)
  }
}

export function postVoiceAction<T = unknown>(actionUrl: string, action: VoiceAction, fields: Record<string, string> = {}) {
  return voiceRequest<T>(actionUrl, {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrfToken()},
    body: new URLSearchParams({action, ...fields}),
  })
}
