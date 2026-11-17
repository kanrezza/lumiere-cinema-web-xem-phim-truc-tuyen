export function bindCheckoutSubmission(form: HTMLFormElement, page: Window = window) {
  const button = form.querySelector<HTMLButtonElement>('[data-payment-submit]')
  const status = form.querySelector<HTMLElement>('[data-payment-status]')
  if (!button || button.disabled || !status) return

  const initialStatus = status.textContent
  let pending = false
  form.addEventListener('submit', event => {
    if (pending) {
      event.preventDefault()
      return
    }
    if (event.defaultPrevented) return
    pending = true
    button.disabled = true
    button.setAttribute('aria-busy', 'true')
    status.textContent = 'Đang chuyển sang VNPay…'
  })

  page.addEventListener('pageshow', () => {
    if (!pending) return
    pending = false
    button.disabled = false
    button.removeAttribute('aria-busy')
    status.textContent = initialStatus
  })
}
