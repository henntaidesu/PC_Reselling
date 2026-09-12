import { ref } from 'vue'

// 缩略图的拖拽排序。两个媒体组件共用这一份，理由和 useFileDrop 一样：各写一份的话，
// 某天只改了其中一处，显卡页和整机页的手感就开始不一样。
//
// 与 useFileDrop 互不打扰：那边只在 dataTransfer 带着 Files 时才接管（从桌面拖文件
// 进来上传），这边拖的是页面里已经有的缩略图，dataTransfer 里没有 Files。所以同一块
// 区域上两套拖放天然分得开，不需要谁去认谁、也不用互相让路。
//
// commit(ids)：拿重排后的完整 id 顺序去落库。**本地顺序已经先改掉了**——拖完立刻看到
// 结果，不等一个请求往返；因此 commit 失败时调用方要自己把列表拉回来，那是只有它才
// 知道怎么做的事，这里不替它猜。
export function useMediaSort(commit) {
  // 正在拖的那一项，以及鼠标此刻悬在哪一项的哪半边
  const source = ref(null)
  const overId = ref(null)
  const after = ref(false)
  // 拖拽起点所属的那个数组。显卡页是五个分类五个数组，跨组拖过去该落在哪没有明确答案
  // （那还意味着换分类），所以直接不受理，让这次拖放落空。
  let sourceList = null

  function reset() {
    source.value = null
    overId.value = null
    after.value = false
    sourceList = null
  }

  // 一律按 id 比对而不是对象引用：列表在 ref / computed 之间转过手，同一条记录未必还是
  // 同一个引用，按引用比会时灵时不灵。
  function apply(list, target) {
    const from = list.findIndex((m) => m.id === source.value.id)
    if (from < 0) return
    const [moved] = list.splice(from, 1)
    // 先删再找目标下标：反过来先算好下标，从前往后拖时会整整差一位
    const to = list.findIndex((m) => m.id === target.id)
    if (to < 0) {
      list.splice(from, 0, moved)   // 目标不在这个数组里，原样放回去
      return
    }
    list.splice(after.value ? to + 1 : to, 0, moved)
    commit(list.map((m) => m.id))
  }

  // 绑在每个格子上：draggable="true" + v-on="sort.handlers(list, item)"
  function handlers(list, item) {
    return {
      dragstart(e) {
        source.value = item
        sourceList = list
        e.dataTransfer.effectAllowed = 'move'
        // 不 setData 的话 Firefox 压根不会启动这次拖拽
        e.dataTransfer.setData('text/plain', String(item.id))
      },
      dragover(e) {
        if (!source.value || sourceList !== list || item.id === source.value.id) return
        e.preventDefault()
        // 别让底下那层投放区也收到：它虽然会因为「没有 Files」自己退出，但 dropEffect
        // 由最后一个处理者说了算，放任不管时光标会在「移动」和「禁止」之间跳。
        e.stopPropagation()
        e.dataTransfer.dropEffect = 'move'
        // 落点按左右半边算。只支持「和目标对调」的话，把最后一张拖到第一位得拖好几次。
        const rect = e.currentTarget.getBoundingClientRect()
        after.value = e.clientX > rect.left + rect.width / 2
        overId.value = item.id
      },
      dragleave() {
        if (overId.value === item.id) overId.value = null
      },
      drop(e) {
        if (!source.value || sourceList !== list) return
        e.preventDefault()
        e.stopPropagation()
        if (item.id !== source.value.id) apply(list, item)
        reset()
      },
      // 拖到空白处松手、中途按 Esc 取消都只会走到这里，状态得在这儿清干净
      dragend: reset
    }
  }

  // 格子的状态类：拖动中的那张淡下去，目标格子在将要插入的那一侧画一条竖线
  function cellClass(item) {
    if (source.value?.id === item.id) return 'sorting'
    if (overId.value !== item.id) return ''
    return after.value ? 'sort-after' : 'sort-before'
  }

  return { handlers, cellClass }
}
