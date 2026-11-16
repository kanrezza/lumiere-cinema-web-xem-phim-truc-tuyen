export type FormFields = Record<string, string | number | boolean>

export function csrfToken(): string {
  return document.querySelector<HTMLInputElement>('[name=csrfmiddlewaretoken]')?.value
    || document.cookie.split('; ').find(item => item.startsWith('csrftoken='))?.slice('csrftoken='.length)
    || ''
}

export function formParams(fields: FormFields) {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(fields)) params.set(name, String(value))
  return params
}

export async function postForm<T>(url: string, fields: FormFields): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formParams(fields),
  })
  if (!response.ok || response.redirected) {
    throw new Error('Yêu cầu bị từ chối. Kiểm tra quyền truy cập hoặc đăng nhập lại.')
  }
  return response.json()
}
