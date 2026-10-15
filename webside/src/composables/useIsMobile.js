import { onMounted, onUnmounted, ref } from 'vue'

function useMediaQuery(query) {
  const matches = ref(false)
  let mq = null

  const update = (e) => { matches.value = e.matches }

  onMounted(() => {
    mq = window.matchMedia(query)
    matches.value = mq.matches
    mq.addEventListener('change', update)
  })
  onUnmounted(() => {
    if (mq) mq.removeEventListener('change', update)
  })

  return matches
}

// 断点 768px，与 App.vue 里的 @media (max-width: 768px) 同一口径——
// 两边不一致时，恰好 768px 宽的设备会一半按手机、一半按电脑渲染。
export function useIsMobile() {
  return { isMobile: useMediaQuery('(max-width: 768px)') }
}

// 「紧凑宽度」：手机加平板（iPad 竖屏 / 横屏、手机横屏），≤1200px。
// 与手机断点是两回事：手机断点管「排版退成单列」，这一档管「宽表格还摆不摆得下」。
// iPad 竖屏减掉 216px 侧栏只剩 550 多像素，十来列的表照样要横滑，所以这些表在这一档
// 就换成卡片列表；而筛选器、弹窗这些仍按 768 走，平板上它们并排是放得下的。
// 页面里对应的 @media 写 (max-width: 1200px)，与概览页栅格退成单列的那一档同值。
export function useIsCompact() {
  return { isCompact: useMediaQuery('(max-width: 1200px)') }
}

// 触屏（没有悬浮能力）。与宽度无关：iPad 很宽但只有手指，窄窗口的桌面浏览器仍有鼠标。
// 目前用于日期选择器的 :editable——Element 的日期框本质是个 <input>，在 iOS 上点一下
// 会同时弹出日历面板和软键盘，键盘把面板顶出视口，而手机上没人会去手敲日期。
export function useIsTouch() {
  return { isTouch: useMediaQuery('(hover: none)') }
}
