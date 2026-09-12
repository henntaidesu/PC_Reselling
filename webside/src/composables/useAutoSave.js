import { computed, nextTick, ref } from 'vue'

// 表单实时自动保存：页面上没有保存按钮，任何改动防抖后自动落盘。
//
// 显卡详情页与整机详情页用的是同一套机制，所以实现只留这一份。它要同时处理三件
// 容易写错的事，每一件出问题都表现为「数据莫名其妙丢了一次」：
//
// 1. 存的过程中用户又改了——保存链跑完一轮会自查 dirty 再存一轮，而不是存完旧值就
//    收工（那样最后一次改动会被静默丢掉）。
// 2. 离开页面时还有没落盘的改动——flush() 把防抖里等着的那次和在途的那次都等完。
// 3. 回填服务端 id、刷新图片角标这类**不是用户编辑**的改动不能反过来触发保存，
//    否则每保存一次就诱发下一次，无限循环。silently() 负责盖住那一轮 watch。
//
// 用法：
//   const autosave = useAutoSave(() => doSave())
//   watch(form, autosave.schedule, { deep: true })
//   载入完数据后 await autosave.begin()   // 跳过「填充表单」引起的那一轮
export function useAutoSave(save, { delay = 600 } = {}) {
  const saving = ref(false)
  const savedOnce = ref(false)
  const dirty = ref(false)
  // 填充表单期间为假：此时的改动来自程序预填，不是用户输入
  const ready = ref(false)
  const inflight = ref(false)

  let timer = null
  let suppress = false

  function schedule() {
    if (!ready.value || suppress) return
    dirty.value = true
    if (timer) clearTimeout(timer)
    timer = setTimeout(run, delay)
  }

  async function run() {
    if (timer) { clearTimeout(timer); timer = null }
    // 同一时刻只跑一条保存链；已在跑时直接返回，正在跑的循环会自查 dirty 继续存
    if (inflight.value || !dirty.value) return
    inflight.value = true
    saving.value = true
    while (dirty.value) {
      dirty.value = false
      try {
        await save()
        savedOnce.value = true
      } catch {
        dirty.value = true   // 存失败，标记未落盘并退出，避免失败死循环
        break
      }
    }
    saving.value = false
    inflight.value = false
  }

  // 立刻存一次，不等防抖。给「必须先落盘才能继续」的操作用：比如要给一个还没存过的
  // 部件传图，得先把那一行建出来拿到 id。
  async function saveNow() {
    if (timer) { clearTimeout(timer); timer = null }
    dirty.value = true
    await run()
    // run() 撞上正在跑的那条链时会直接返回，这里等它跑完，调用方拿到的才是最新结果
    while (inflight.value) {
      await new Promise((r) => setTimeout(r, 40))
    }
  }

  // 离开页面前把还没落盘的改动彻底存完（含防抖里等着的和在途的那次）
  async function flush() {
    if (timer) { clearTimeout(timer); timer = null }
    run()
    while (inflight.value) {
      await new Promise((r) => setTimeout(r, 40))
    }
  }

  // 程序自己改表单（回填 id、更新角标）时包一层，绕开这一轮自动保存。
  // 深层 watch 是 pre 刷新的，改完 await 一次 nextTick 就能盖住它那一轮。
  async function silently(mutate) {
    suppress = true
    mutate()
    await nextTick()
    suppress = false
  }

  // 数据填进表单之后调用：等填充引起的那波 watch 冲刷完，再开启自动保存
  async function begin() {
    await nextTick()
    dirty.value = false
    ready.value = true
  }

  function pause() {
    ready.value = false
    if (timer) { clearTimeout(timer); timer = null }
  }

  return {
    saving,
    savedOnce,
    // 有改动还没落盘（等着存、或正在存）
    pending: computed(() => dirty.value || inflight.value),
    schedule,
    saveNow,
    flush,
    silently,
    begin,
    pause
  }
}
