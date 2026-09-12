<template>
  <div class="ifield" :class="{ 'ifield--stack': stack, 'ifield--readonly': readonly }">
    <span class="ifield-label">{{ label }}</span>
    <div class="ifield-value">
      <slot />
    </div>
  </div>
</template>

<script setup>
// 详情页里的一行「标签 + 可直接编辑的值」。
//
// 详情页就是编辑页：这里不做「点一下才变成输入框」的切换态——多一次点击换来的只是
// 看起来干净，代价是每改一个字段都要先猜「这块能不能点」。所以控件一直在，只是平时
// 长得像文本（无边框、无底色），鼠标移上去才浮出边框提示可改。
//
// 控件由调用方放进插槽（el-input / el-select / el-date-picker / MoneyInput 都行），
// 这里只负责版式和「像文本」的那层皮。
defineProps({
  label: { type: String, default: '' },
  // 值太长（备注、链接）时标签单独一行，值占满宽度
  stack: { type: Boolean, default: false },
  // 只读行（汇率快照这类算出来的值）：不画悬浮边框，免得让人以为能改
  readonly: { type: Boolean, default: false }
})
</script>

<style scoped>
.ifield {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 5px 0;
  font-size: 14px;
  /* 与「padding + 32px 的控件」等高。只读行里没有控件，不给下限的话它会比上下两行
     矮一截，一列字段的行距就时宽时窄 */
  min-height: 42px;
}
.ifield-label {
  color: #8a94a6;
  flex: 0 0 auto;
  /* 标签给一个下限宽度：中文标签 2~5 个字不等，不给下限的话每行输入框的左边缘都在
     不同位置，一列字段看着像被揉过。比它长的标签（英文 / 日文里有）照旧把输入框往
     右推，不截断——宁可那一行错开，也不要把标签切掉。 */
  min-width: 76px;
  white-space: nowrap;
}
.ifield-value {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  justify-content: flex-start;
  color: #e6edf7;
}
.ifield--stack { flex-direction: column; align-items: stretch; gap: 4px; }

/* ── 「像文本」的输入控件 ──────────────────────────────────────────────
   Element 的输入框用 inset box-shadow 画边框，所以要压掉的是 box-shadow 而不是
   border；自己的那一层 border 始终占位（transparent），否则悬浮时浮出边框会把
   整行撑高 1px，鼠标扫过一列字段就是一串抖动。 */
.ifield-value :deep(.el-input__wrapper),
.ifield-value :deep(.el-select__wrapper),
.ifield-value :deep(.el-textarea__inner) {
  background-color: transparent !important;
  box-shadow: none !important;
  border: 1px solid transparent;
  border-radius: 6px;
  padding-left: 8px;
  padding-right: 8px;
  transition: border-color 0.15s, background-color 0.15s;
}
/* border-color 必须带 !important：App.vue 里有一条全局的
   `.el-input__wrapper { border-color: #2a3446 !important }`，不压过它，
   悬浮和聚焦时边框颜色根本不会变，鼠标点进哪个框全靠猜。 */
.ifield-value :deep(.el-input__wrapper:hover),
.ifield-value :deep(.el-select__wrapper:hover),
.ifield-value :deep(.el-textarea__inner:hover) {
  border-color: #3d4d6b !important;
  background-color: rgba(91, 140, 255, 0.05) !important;
}
.ifield-value :deep(.el-input__wrapper.is-focus),
.ifield-value :deep(.el-select__wrapper.is-focused),
.ifield-value :deep(.el-textarea__inner:focus) {
  border-color: var(--pcr-accent) !important;
  background-color: rgba(91, 140, 255, 0.07) !important;
}
/* 值一律左对齐，紧贴输入框的左内边距。一列字段扫下来，所有值的起点是同一条竖线，
   长短不一的内容也不会各自从不同的位置往左散开 */
.ifield-value :deep(.el-input__inner) {
  text-align: left;
  color: #e6edf7;
  font-weight: 500;
}
/* 日期框前面的小日历图标在这里只是噪点：这一行的标签已经写明是什么日期 */
.ifield-value :deep(.el-input__prefix) { display: none; }
/* 下拉的收起箭头平时藏起来，悬浮 / 展开时才出现——一列字段右边挂一排箭头太吵 */
.ifield-value :deep(.el-select__suffix) { opacity: 0; transition: opacity 0.15s; }
.ifield-value :deep(.el-select__wrapper:hover .el-select__suffix),
.ifield-value :deep(.el-select__wrapper.is-focused .el-select__suffix) { opacity: 0.7; }
/* 下拉的值和输入框的文字排成同一条竖线。选中的值落在 .el-select__placeholder 里
   （Element Plus 的新 select 就是这么渲染的，不是只有占位符才用这个类），它是个铺满
   整格的 span，只给外面的 flex 容器设对齐管不到里面的文字，所以这里要直接给 text-align。 */
.ifield-value :deep(.el-select__selection) { justify-content: flex-start; }
.ifield-value :deep(.el-select__placeholder),
.ifield-value :deep(.el-select__input) { text-align: left; }
.ifield-value :deep(.el-select__selected-item) { color: #e6edf7; font-weight: 500; }
.ifield-value :deep(.el-select__placeholder.is-transparent) { color: #5a6478; }
.ifield-value :deep(.el-input.is-disabled .el-input__inner) {
  color: #a6adb4;
  -webkit-text-fill-color: #a6adb4;
}
/* 只读行没有输入框，用同样的左内边距（8px 内边距 + 1px 透明边框）把文字顶到
   和上下行的值一条线上 */
.ifield--readonly .ifield-value { padding-left: 9px; font-weight: 500; }

/* 控件一律撑满可用宽度，右对齐的文字才会和其它行对齐 */
.ifield-value :deep(.el-input),
.ifield-value :deep(.el-select),
.ifield-value :deep(.el-date-editor) { width: 100% !important; }
</style>
