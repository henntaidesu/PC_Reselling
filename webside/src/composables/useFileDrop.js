import { ref } from 'vue'

// 把一块区域变成「拖文件进来松手就传」的投放区。两个媒体组件共用这一份：
// 显卡按分类分了五个网格（MediaManager），整机与部件各是一个平铺网格（MediaGallery），
// 各写一份的话某天只改了其中一处，两边的拖拽行为就不一样了。
//
// 这里处理的是 HTML5 拖放的两个坑：
//   1. dragenter / dragleave 会在子元素之间来回冒泡——鼠标从格子挪到格子缝隙也会触发
//      一次 dragleave，只用一个布尔量做高亮会疯狂闪烁。所以按进出计数，归零才算真离开。
//   2. dragover 不 preventDefault 的话浏览器根本不允许 drop，光标一直是禁止符号。
//      反过来，区域不可用时就**不要** preventDefault，让这次拖放落空而不是悄悄吞掉。
//
// onFiles(files, rejected)：files 是过了 accept 的那些，rejected 是被滤掉的个数
// （用户拖了一个 .zip 进来，总得告诉他为什么没反应）。
export function useFileDrop(onFiles, options = {}) {
  const accept = options.accept || /^(image|video)\//
  const disabled = options.disabled || (() => false)

  const dragging = ref(false)
  let depth = 0

  function reset() {
    depth = 0
    dragging.value = false
  }

  // 只认文件。页面里拖一张已有的缩略图、拖一段文字，都不该让投放区亮起来
  function hasFiles(e) {
    return Array.from(e.dataTransfer?.types || []).includes('Files')
  }

  function onDragEnter(e) {
    if (disabled() || !hasFiles(e)) return
    e.preventDefault()
    depth += 1
    dragging.value = true
  }

  function onDragOver(e) {
    if (disabled() || !hasFiles(e)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }

  function onDragLeave() {
    if (!dragging.value) return
    depth -= 1
    if (depth <= 0) reset()
  }

  function onDrop(e) {
    if (disabled() || !hasFiles(e)) return
    e.preventDefault()
    reset()
    const all = Array.from(e.dataTransfer?.files || [])
    const files = all.filter((f) => accept.test(f.type))
    onFiles(files, all.length - files.length)
  }

  return {
    dragging,
    // 直接 v-on="handlers" 绑到投放区那一层
    handlers: {
      dragenter: onDragEnter,
      dragover: onDragOver,
      dragleave: onDragLeave,
      drop: onDrop
    }
  }
}
