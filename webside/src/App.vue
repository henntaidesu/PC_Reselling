<template>
  <el-config-provider :locale="elementLocale">
    <router-view />
  </el-config-provider>
</template>

<script setup>
import { ElConfigProvider } from 'element-plus'
import { elementLocale } from '@/i18n'
</script>

<style>
/* 深色主题地基，配色与 FreeMarket_Manager 对齐：底 #0b1220 / 卡片 #131c2f */
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root.dark {
  color-scheme: dark;
}

:root {
  --app-vh: 1vh;
  --pcr-bg: #0b1220;
  --pcr-card: #131c2f;
  --pcr-card-header: #161f33;
  --pcr-border: #28354a;
  --pcr-text: #e6edf7;
  --pcr-text-dim: #a6adb4;
  --pcr-accent: #5b8cff;
  --pcr-profit: #4ade80;
  --pcr-loss: #f87171;
}

@supports (height: 1dvh) {
  :root { --app-vh: 1dvh; }
}

html.dark {
  --el-bg-color: #0b1220;
  --el-bg-color-page: #0b1220;
  --el-fill-color-blank: #131c2f;
  --el-fill-color-light: #18233a;
  --el-mask-color: rgba(11, 18, 32, 0.78);
}

html, body, #app {
  height: 100%;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  background: var(--pcr-bg);
  color: #e5e7eb;
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-thumb { background: #3a4456; border-radius: 3px; }
::-webkit-scrollbar-track { background: transparent; }

.page-title { color: #e6edf7 !important; }

.el-card, .el-dialog, .el-table,
.el-input__wrapper, .el-select__wrapper, .el-textarea__inner {
  border-color: #2a3446 !important;
}

.el-card {
  background: #131c2f !important;
  color: #e6edf7;
}
.el-card__header {
  background: #161f33 !important;
  border-bottom: 1px solid #28354a !important;
  color: #e6edf7 !important;
}
.el-card__body { background: transparent !important; color: #e6edf7; }

/* 详情页的「左表单 / 右图片」分栏：宽度 4 : 6，两列等高。
   整机页和每个部件的卡片用的是同一套——分头各写一份的话，某天调了其中一处，
   同一个页面上下两块的比例就对不上了。
   用 flex-grow 的比例而不是百分比宽度：中间 16px 的间隙不会被算进去。
   两列被 stretch 拉成等高，卡片再填满自己那一列，右边图片少时也不会矮一截。 */
.pcr-split { display: flex; align-items: stretch; gap: 16px; }
.pcr-split > * { display: flex; min-width: 0; }
.pcr-split > * > .el-card { width: 100%; }
.pcr-split-form { flex: 4 1 0; }
.pcr-split-media { flex: 6 1 0; }
/* 右栏那张图片卡：两栏等高是 align-items: stretch 撑出来的，但 el-card 不会把多出来的
   高度分给 body——卡片下半截的空白于是不属于任何元素，拖文件到那儿松手毫无反应，而那里
   看着恰恰最像「能往里丢东西」的地方。把高度一路传下去，让 MediaGallery 能撑满整张卡，
   投放区也就覆盖整张卡而不只是缩略图那一行。 */
.pcr-split-media > .el-card { display: flex; flex-direction: column; }
.pcr-split-media > .el-card > .el-card__body { flex: 1 1 auto; display: flex; flex-direction: column; }
@media (max-width: 1100px) {
  /* 窄屏并排都挤没了，改成上下排 */
  .pcr-split { flex-direction: column; }
}

.el-loading-mask { background-color: var(--el-mask-color) !important; }
.el-loading-mask .el-loading-spinner .path { stroke: #8fb8ff; }

.el-table {
  --el-table-header-bg-color: #18233a;
  --el-table-tr-bg-color: #131c2f;
  --el-table-row-hover-bg-color: #1b2942;
  --el-table-border-color: #28354a;
  color: #d6deea;
}
.el-dialog { --el-dialog-bg-color: #131c2f; }

/* iOS 文本自动放大 / 链式滚动 / 点击高亮，三个移动端通病一并按 FreeMarket 的做法压掉 */
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
html, body { overscroll-behavior: none; }
body { -webkit-tap-highlight-color: transparent; }

@media (max-width: 768px) {
  /* iOS 聚焦 <16px 的输入框会强行放大整页且不复位——所有输入类控件手机上一律 16px */
  .el-input__inner, .el-input__wrapper, .el-textarea__inner,
  .el-select__wrapper, .el-select__placeholder {
    font-size: 16px;
  }
  .el-dialog {
    --el-dialog-margin-top: 5vh;
    width: 94vw !important;
    max-width: 94vw;
  }
  /* 弹窗表单一律标签在上，窄屏下不挤成一条 */
  .el-dialog .el-form-item { display: block; }
  .el-dialog .el-form-item__label {
    width: auto !important;
    justify-content: flex-start;
    text-align: left;
    padding: 0 0 4px;
  }
  .el-dialog .el-form-item__content { margin-left: 0 !important; }
  .el-card__body { padding: 12px; }
  .el-card__header { padding: 12px; }
  .el-table { font-size: 12px; }
  @media (hover: none) {
    .el-table { --el-table-row-hover-bg-color: transparent; }
  }
}

/* 通用工具类 */
.pcr-profit { color: var(--pcr-profit); }
.pcr-loss { color: var(--pcr-loss); }
.pcr-dim { color: var(--pcr-text-dim); }
.pcr-mono { font-variant-numeric: tabular-nums; }
</style>
