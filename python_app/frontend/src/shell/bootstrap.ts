(() => {
  let theme = 'dark'
  try {
    if (window.localStorage.getItem('lumiere-theme') === 'light') theme = 'light'
  } catch { /* Dark is the default if browser storage is unavailable. */ }
  document.documentElement.dataset.theme = theme
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  if (meta) meta.content = theme === 'light' ? '#f6f5f1' : '#0b0d0e'
})()
