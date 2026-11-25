/** Keep a moderation confirmation inside the auditorium, including fullscreen. */
export function confirmRoomKick(room: HTMLElement, name: string): Promise<boolean> {
  return new Promise(resolve => {
    const dialog = document.createElement('dialog')
    dialog.className = 'cinema-kick-confirm'
    dialog.setAttribute('aria-labelledby', 'cinema-kick-title')
    const title = document.createElement('h2')
    title.id = 'cinema-kick-title'
    title.textContent = `Loại ${name} khỏi phòng?`
    const description = document.createElement('p')
    description.textContent = 'Người này sẽ rời buổi chiếu và không thể vào lại bằng liên kết phòng.'
    const actions = document.createElement('div')
    const cancel = document.createElement('button')
    cancel.type = 'button'
    cancel.className = 'btn secondary small'
    cancel.textContent = 'Giữ lại'
    const confirm = document.createElement('button')
    confirm.type = 'button'
    confirm.className = 'btn small'
    confirm.textContent = 'Loại khỏi phòng'
    actions.append(cancel, confirm)
    dialog.append(title, description, actions)
    room.append(dialog)
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const listeners = new AbortController()
    let settled = false
    const finish = (accepted: boolean) => {
      if (settled) return
      settled = true
      listeners.abort()
      if (dialog.open) dialog.close()
      dialog.remove()
      if (previous?.isConnected) previous.focus({preventScroll: true})
      resolve(accepted)
    }
    cancel.addEventListener('click', () => finish(false), {signal: listeners.signal})
    confirm.addEventListener('click', () => finish(true), {signal: listeners.signal})
    dialog.addEventListener('cancel', event => {event.preventDefault(); finish(false)}, {signal: listeners.signal})
    dialog.addEventListener('close', () => finish(false), {signal: listeners.signal})
    document.addEventListener('lumiere:stop', () => finish(false), {signal: listeners.signal})
    window.addEventListener('pagehide', () => finish(false), {signal: listeners.signal})
    try {dialog.showModal(); cancel.focus()} catch {finish(false)}
  })
}
