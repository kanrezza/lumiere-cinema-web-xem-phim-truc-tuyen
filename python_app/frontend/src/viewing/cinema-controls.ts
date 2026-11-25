type FullscreenDocument = Document & {
  webkitFullscreenElement?: Element | null
  webkitExitFullscreen?: () => Promise<void> | void
}
type FullscreenRoom = HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void }

/** Screen and room controls never alter the shared playback state. */
export function initCinemaControls(room: HTMLElement) {
  const button = room.querySelector<HTMLButtonElement>('[data-cinema-fullscreen]')
  const label = button?.querySelector<HTMLElement>('[data-cinema-fullscreen-label]')
  const status = room.querySelector<HTMLElement>('#room-status')
  const approvalButton = room.querySelector<HTMLButtonElement>('[data-room-approval-toggle]')
  const approvalDialog = room.querySelector<HTMLDialogElement>('[data-room-approval-dialog]')
  const approvalClose = approvalDialog?.querySelector<HTMLButtonElement>('[data-room-approval-close]')
  const doc = document as FullscreenDocument
  const target = room as FullscreenRoom
  const events = new AbortController()
  let busy = false
  let disposed = false
  let previousFocus: HTMLElement | null = null
  let fallback = false
  let previousOverflow = document.body.style.overflow
  let fullscreenNotice = ''

  function clearFullscreenNotice() {
    if (status && fullscreenNotice && status.textContent === fullscreenNotice) status.textContent = ''
    fullscreenNotice = ''
  }

  function announceFullscreen(message: string) {
    fullscreenNotice = message
    if (status) status.textContent = message
  }

  function isFullscreen() {
    return doc.fullscreenElement === room || doc.webkitFullscreenElement === room || fallback
  }

  function renderFullscreen() {
    const active = isFullscreen()
    if (label) label.textContent = active ? 'Thu nhỏ rạp' : 'Phóng to rạp'
    button?.setAttribute('aria-pressed', String(active))
    button?.setAttribute('title', active ? 'Thoát chế độ toàn màn hình' : 'Mở rạp toàn màn hình')
  }

  function exitFallback() {
    fallback = false
    room.classList.remove('is-immersive')
    document.body.style.overflow = previousOverflow
    clearFullscreenNotice()
    renderFullscreen()
  }

  function fullscreenMatches(entering: boolean) {
    return entering ? isFullscreen() : !doc.fullscreenElement && !doc.webkitFullscreenElement && !fallback
  }

  function waitForFullscreenTransition(entering: boolean) {
    if (fullscreenMatches(entering) || disposed) return Promise.resolve()
    return new Promise<void>(resolve => {
      let finished = false
      const finish = () => {
        if (finished) return
        finished = true
        window.clearTimeout(timeout)
        doc.removeEventListener('fullscreenchange', changed)
        doc.removeEventListener('webkitfullscreenchange', changed)
        events.signal.removeEventListener('abort', finish)
        resolve()
      }
      const changed = () => { if (fullscreenMatches(entering)) finish() }
      const timeout = window.setTimeout(finish, 180)
      doc.addEventListener('fullscreenchange', changed)
      doc.addEventListener('webkitfullscreenchange', changed)
      events.signal.addEventListener('abort', finish, {once: true})
    })
  }

  async function toggleFullscreen() {
    if (busy || disposed) return
    busy = true
    const entering = !(fallback || doc.fullscreenElement || doc.webkitFullscreenElement)
    let keepNotice = false
    try {
      if (fallback) exitFallback()
      else if (doc.fullscreenElement) await doc.exitFullscreen()
      else if (doc.webkitFullscreenElement && doc.webkitExitFullscreen) await doc.webkitExitFullscreen()
      else if (target.requestFullscreen) await target.requestFullscreen()
      else if (target.webkitRequestFullscreen) await target.webkitRequestFullscreen()
      else {
        previousOverflow = document.body.style.overflow
        fallback = true
        room.classList.add('is-immersive')
        document.body.style.overflow = 'hidden'
        announceFullscreen('Trình duyệt chưa hỗ trợ toàn màn hình cho rạp. Đã mở rạp kín vùng xem; nhấn Esc để thu nhỏ.')
        keepNotice = true
      }
      if (!keepNotice) clearFullscreenNotice()
    } catch {
      // Embedded browsers can reject the promise after completing the transition.
      await waitForFullscreenTransition(entering)
      if (!disposed) {
        if (fullscreenMatches(entering)) clearFullscreenNotice()
        else announceFullscreen(entering
          ? 'Trình duyệt chưa cho phép mở toàn màn hình. Hãy bấm Phóng to rạp để thử lại.'
          : 'Chưa thể thoát toàn màn hình. Nhấn Esc hoặc thử Thu nhỏ rạp lần nữa.')
      }
    } finally {
      busy = false
      if (!disposed) renderFullscreen()
    }
  }

  function closeApproval() {
    if (!approvalDialog) return
    if (approvalDialog.open) approvalDialog.close()
  }

  function restoreApprovalFocus() {
    approvalButton?.setAttribute('aria-expanded', 'false')
    if (!disposed) (previousFocus || approvalButton)?.focus({preventScroll: true})
    previousFocus = null
  }

  function openApproval() {
    if (!approvalDialog || !approvalButton || disposed) return
    if (approvalDialog.open) {
      closeApproval()
      return
    }
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : approvalButton
    try {
      approvalDialog.showModal()
      approvalButton.setAttribute('aria-expanded', 'true')
      approvalClose?.focus({preventScroll: true})
    } catch {
      if (status) status.textContent = 'Không thể mở mục duyệt thành viên. Hãy tải lại trang rồi thử lại.'
    }
  }

  button?.addEventListener('click', toggleFullscreen, {signal: events.signal})
  const fullscreenChanged = () => {clearFullscreenNotice(); renderFullscreen()}
  document.addEventListener('fullscreenchange', fullscreenChanged, {signal: events.signal})
  document.addEventListener('webkitfullscreenchange', fullscreenChanged, {signal: events.signal})
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && fallback && !approvalDialog?.open) {
      event.preventDefault()
      exitFallback()
      button?.focus({preventScroll: true})
    }
  }, {signal: events.signal})
  approvalButton?.addEventListener('click', openApproval, {signal: events.signal})
  approvalClose?.addEventListener('click', closeApproval, {signal: events.signal})
  approvalDialog?.addEventListener('close', restoreApprovalFocus, {signal: events.signal})
  approvalDialog?.addEventListener('click', event => {
    if (event.target !== approvalDialog) return
    const rect = approvalDialog.getBoundingClientRect()
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeApproval()
  }, {signal: events.signal})
  renderFullscreen()

  const dispose = () => {
    disposed = true
    closeApproval()
    if (fallback) exitFallback()
    events.abort()
  }
  window.addEventListener('pagehide', dispose, {once: true, signal: events.signal})
  return dispose
}
