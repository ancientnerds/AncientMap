// NERV cursor for studio platform takes (pipeline/studio/capture/platform.py).
// A CDP screencast never contains the OS cursor, so the take draws its own:
// a cyan ring that follows the mouse and a ripple on every click. Injected
// with context.add_init_script on ?demo=1&video=1 pages only.
(() => {
  const add = () => {
    if (document.getElementById('__nerv_cursor')) return
    const style = document.createElement('style')
    style.textContent = `
      #__nerv_cursor{position:fixed;left:-100px;top:-100px;width:26px;height:26px;margin:-13px 0 0 -13px;
        border:2px solid #20F0FF;border-radius:50%;box-shadow:0 0 10px #20F0FF,inset 0 0 6px rgba(32,240,255,.5);
        pointer-events:none;z-index:2147483647;transition:transform .08s}
      #__nerv_cursor::after{content:"";position:absolute;left:50%;top:50%;width:4px;height:4px;margin:-2px 0 0 -2px;
        background:#20F0FF;border-radius:50%}
      .__nerv_ripple{position:fixed;width:26px;height:26px;margin:-13px 0 0 -13px;border:2px solid #20F0FF;
        border-radius:50%;pointer-events:none;z-index:2147483646;animation:__nerv_rip .6s ease-out forwards}
      @keyframes __nerv_rip{to{transform:scale(3);opacity:0}}`
    document.head.appendChild(style)
    const cursor = document.createElement('div')
    cursor.id = '__nerv_cursor'
    document.body.appendChild(cursor)
    addEventListener('mousemove', (e) => {
      cursor.style.left = `${e.clientX}px`
      cursor.style.top = `${e.clientY}px`
    }, true)
    addEventListener('mousedown', (e) => {
      cursor.style.transform = 'scale(.75)'
      const ripple = document.createElement('div')
      ripple.className = '__nerv_ripple'
      ripple.style.left = `${e.clientX}px`
      ripple.style.top = `${e.clientY}px`
      document.body.appendChild(ripple)
      setTimeout(() => ripple.remove(), 700)
    }, true)
    addEventListener('mouseup', () => {
      cursor.style.transform = 'none'
    }, true)
  }
  if (document.readyState === 'loading') addEventListener('DOMContentLoaded', add)
  else add()
})()
