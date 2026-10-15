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

/* ── 详情弹窗（views/Cards 持有，内容是 CardDetail / DeviceDetail）──────────
   el-dialog 被 teleport 到 body 下，页面里的 scoped 样式够不着，只能写在这里。
   弹窗是**定高**的，自己不滚动：里面的 DetailShell 把字段平铺在几张卡片里，次要内容
   收进一张在卡内滚动的标签页卡。Element 自带的标题栏不用（DetailShell 有自己的顶栏），
   内边距清零交给骨架自己管。 */
.pcr-detail-dialog {
  padding: 0;
  height: min(860px, 92vh);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.pcr-detail-dialog .el-dialog__header { display: none; }
.pcr-detail-dialog .el-dialog__body { flex: 1 1 auto; min-height: 0; padding: 0; }
@media (max-width: 768px) {
  /* 手机上是全屏弹窗：下面那条「el-dialog 一律 94vw」会把全屏也压窄，这里抬回来 */
  .pcr-detail-dialog.is-fullscreen { width: 100vw !important; max-width: 100vw; height: 100%; }
}

/* ── 详情模块里的表单：标签在上、两列网格 ──────────────────────────────
   模块页是定高的，一个模块里的字段要在一屏内排完，所以按两列排；标签放上面而不是
   左边，两列各自的输入框才有足够宽度（「币种 + 金额」那种组合控件左标签时排不下）。
   .pcr-span-2 占满整行（备注、链接这类长值）。
   .pcr-ro 是只读值（汇率快照这类算出来的数）：和输入框同高、不画边框，
   一眼分得出哪些能改。 */
.pcr-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 20px; }
.pcr-form .el-form-item { margin-bottom: 14px; }
.pcr-form .el-form-item__label { color: #8a94a6; line-height: 20px; margin-bottom: 4px !important; padding: 0 !important; }
.pcr-form .el-select,
.pcr-form .el-date-editor.el-input,
.pcr-form .el-date-editor { width: 100% !important; }
.pcr-span-2 { grid-column: 1 / -1; }
.pcr-ro {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0 4px;
  min-height: 32px;
  width: 100%;
  padding: 0 11px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.025);
  color: #e6edf7;
  font-size: 14px;
}
/* 模块里的小节标题（一个模块里分两三块时用），比卡片标题轻 */
.pcr-sec-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #c9d3e3;
  letter-spacing: 0.3px;
}
@media (max-width: 768px) {
  .pcr-form { grid-template-columns: minmax(0, 1fr); }
}

/* ── 详情弹窗里的分区卡片（DetailShell 的插槽内容用，显卡 / 整机共用）────────
   版式照 FreeMarket_Manager 库存管理的商品表单，追求一屏看全：
   .pd-card        分区卡片；.pd-card-head / -title 卡片标题行，.pd-badge 标题旁的小徽章
   .pd-form        紧凑表单（配 size="small"，30px 高、12px 标签、行距 10px）
   .pd-row         flex 折行的一排字段，每个字段由页面自己给基准宽度（.f-*）
   .pd-grid        等宽网格（默认两列，--pd-cols 改列数）
   .pd-tabs-card   最下面那张标签页卡：吃掉剩余高度，.pd-tab-body 在卡内滚
   .pd-stat        顶栏的总账药丸；.pd-settle 结算明细
   写在全局是因为它们出现在页面传给 DetailShell 的插槽里，两份页面的 scoped 各抄一遍
   的下场是改了一边另一边对不上。 */
.pd-card {
  flex: none;
  padding: 8px 12px 0;
  border: 1px solid var(--pcr-border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  min-width: 0;
}
.pd-card-head { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 8px; min-height: 20px; margin-bottom: 6px; }
.pd-card-title { font-size: 12.5px; font-weight: 600; letter-spacing: 0.04em; color: #a4aec1; }
.pd-card-extra { margin-left: auto; font-size: 12px; color: #8a94a6; }
.pd-badge {
  padding: 0 7px;
  border-radius: 8px;
  background: rgba(91, 140, 255, 0.12);
  color: #cbd5e1;
  font-size: 11.5px;
  line-height: 18px;
}
.pd-badge--warn { background: rgba(230, 162, 60, 0.14); color: #e6a23c; }
.pd-count {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 9px;
  background: rgba(91, 140, 255, 0.16);
  color: #cbd5e1;
  font-size: 11px;
  line-height: 17px;
}
/* 两张卡并排（显卡的购入 / 出售） */
.pd-pair { flex: none; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }

.pd-form .el-form-item { margin-bottom: 10px; }
.pd-form .el-form-item__label {
  padding: 0 0 3px !important;
  margin-bottom: 0 !important;
  font-size: 12px;
  line-height: 1.35;
  letter-spacing: 0.02em;
  color: #99a3b6;
}
/* 13px 只给桌面：手机上输入框必须 16px（见下方 iOS 那条），这里特异度更高会把它压回去 */
@media (min-width: 769px) {
  .pd-form .el-input--small,
  .pd-form .el-select--small .el-select__wrapper { font-size: 13px; }
  .pd-form .el-textarea__inner { font-size: 13px; line-height: 1.6; }
}
.pd-form .el-select,
.pd-form .el-date-editor.el-input,
.pd-form .el-date-editor { width: 100% !important; }
.pd-form .pcr-ro { min-height: 30px; font-size: 13px; padding: 0 9px; }
.pd-row { display: flex; flex-wrap: wrap; align-items: flex-start; column-gap: 10px; }
.pd-row > .el-form-item { min-width: 0; }
.pd-grid { display: grid; grid-template-columns: repeat(var(--pd-cols, 2), minmax(0, 1fr)); column-gap: 10px; }

.pd-tabs-card {
  flex: 1 1 auto;
  min-height: 160px;
  display: flex;
  flex-direction: column;
  padding: 2px 12px 0;
  container-type: inline-size;
}
.pd-tabbar { flex: none; }
.pd-tabbar .el-tabs__header { margin: 0; }
.pd-tabbar .el-tabs__content { display: none; }
.pd-tabbar .el-tabs__nav-wrap::after { height: 1px; background: var(--pcr-border); }
.pd-tabbar .el-tabs__item { height: 34px; font-size: 13px; }
.pd-tab-body { flex: 1 1 auto; min-height: 0; overflow: auto; padding: 10px 0; }
.pd-tab-body--split { overflow: hidden; padding: 0; }

.pd-sub-title { font-size: 12.5px; font-weight: 600; letter-spacing: 0.04em; color: #a4aec1; margin-bottom: 8px; }
.pd-sub-label { font-size: 12px; color: #99a3b6; margin-bottom: 6px; }
.pd-note { font-size: 12px; margin: 4px 0 0; line-height: 1.6; color: #8a94a6; }

.pd-stat {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--pcr-border);
  background: rgba(0, 0, 0, 0.18);
}
.pd-stat-k { font-size: 11.5px; color: #8a94a6; }
.pd-stat-v { font-size: 13.5px; font-weight: 600; color: #e6edf7; }
.pd-stat-sub { font-size: 11.5px; color: #8a94a6; }
.pd-stat.is-up { border-color: rgba(103, 194, 58, 0.4); background: rgba(103, 194, 58, 0.08); }
.pd-stat.is-up .pd-stat-v { color: #85ce61; }
.pd-stat.is-down { border-color: rgba(245, 108, 108, 0.45); background: rgba(245, 108, 108, 0.1); }
.pd-stat.is-down .pd-stat-v { color: #f89898; }
.pd-flag { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; padding: 2px 8px; border-radius: 6px; }
.pd-flag.done { color: #67c23a; background: rgba(103, 194, 58, 0.1); }
.pd-flag.warn { color: #e6a23c; background: rgba(230, 162, 60, 0.1); }

.pd-settle {
  padding: 8px 12px;
  border: 1px solid var(--pcr-border);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.15);
}
.pd-settle-row { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; font-size: 13px; }
.pd-settle-row > span { color: #8a94a6; }
.pd-settle-row > b { color: #e6edf7; font-size: 13.5px; }
.pd-settle-sum { border-top: 1px dashed var(--pcr-border); margin-top: 3px; padding-top: 7px; }
.pd-settle-big > b { font-size: 17px; }

@media (max-width: 768px) {
  .pd-pair { grid-template-columns: minmax(0, 1fr); }
  .pd-row > .el-form-item { flex: 1 1 100% !important; max-width: none !important; }
  .pd-grid { grid-template-columns: minmax(0, 1fr); }
  .pd-tabs-card { flex: none; min-height: 0; }
  .pd-tab-body, .pd-tab-body--split { overflow: visible; }
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
  /* 控件整体抬高一档。32px 是给鼠标用的尺寸，手指按不准——一列字段挨着排时，
     点「购入日期」经常落进上一行的「型号」。40px 加上行间距刚好够一个指腹。
     改的是 Element 的尺寸变量而不是各处写死高度：输入框、下拉、默认按钮一起长高，
     表格里的 size="small" 走的是另一个变量，不受影响（它在横向滚动区里，越矮越好）。
     选择器写成 html:root 而不是 :root：Element 自己这两个变量也定义在 :root 上，
     同特异度就只能靠打包顺序取胜——加个 html 把特异度抬高一档，谁先谁后都无所谓。 */
  html:root {
    --el-component-size: 40px;
    --el-component-size-large: 44px;
  }
  .el-dialog {
    --el-dialog-margin-top: 5vh;
    width: 94vw !important;
    max-width: 94vw;
  }
  /* 确认框（删除部件 / 删除注资那几处）默认写死 420px，比 360px 的屏还宽——
     两侧被裁掉之后，「取消 / 确定」正好是最先被切走的那部分。
     它不是 el-dialog，不吃上面那条规则，得单独给。 */
  .el-message-box { --el-messagebox-width: 94vw; }
  /* 标签在左的表单一律改成标签在上。label-width 是个死宽度：Settings 那张表单写的
     150px，在 360px 的屏上先被标签吃掉将近一半，剩给输入框的位置连一个图床 URL 的
     开头都放不下。本来就是 label-position="top" 的（各个弹窗）不受这条影响。 */
  .el-form--label-left .el-form-item,
  .el-form--label-right .el-form-item { display: block; }
  .el-form--label-left .el-form-item__label,
  .el-form--label-right .el-form-item__label {
    width: auto !important;
    justify-content: flex-start;
    text-align: left;
    padding: 0 0 4px;
  }
  .el-form--label-left .el-form-item__content,
  .el-form--label-right .el-form-item__content { margin-left: 0 !important; }
  .el-card__body { padding: 12px; }
  .el-card__header { padding: 12px; }
  .el-table { font-size: 12px; }
  /* 弹窗底部按钮排成一行，各占一半——「取消 / 保存」在窄屏上挤在右下角，
     两个都只有指甲盖大，点错的概率不低 */
  .el-dialog__footer .el-button { flex: 1 1 0; margin-left: 0; }
  .el-dialog__footer { display: flex; gap: 10px; }
}

/* ── 触屏：悬浮态在这里等于不存在 ──────────────────────────────────────
   判据是「这块屏能不能悬浮」，不是它有多宽，所以用 (hover: none) 而不是宽度断点：
   窄窗口的桌面浏览器仍有鼠标，那套「移上去才亮」的皮该留着。 */
@media (hover: none) {
  /* 表格行的悬浮底色在触屏上只会在点过之后赖着不走，看着像选中了某一行 */
  .el-table { --el-table-row-hover-bg-color: transparent; }
  /* 表格里的图标按钮（编辑 / 删除）只有图标那么大，手指点不中还容易点到隔壁那个。
     只加内边距不动图标尺寸：热区撑到 30px 见方，行高不变。 */
  .el-table .el-button.is-link,
  .el-table .el-button.is-text { padding: 7px 5px; height: auto; }

  /* 当二级菜单用的 el-tabs（整机详情的部件类型、系统配置的五块）：Element 溢出时靠
     「平移 nav + 两端 20px 的小箭头」翻页，手指划不动、箭头又点不准，手机上等于只看得见
     前几个标签。挂上 .pcr-touch-tabs 就改成原生横向滚动，箭头藏掉。
     注意 nav 的 transform 被压掉之后，Element 也不会再替你把选中项挪进可视区——
     可能从别处直接跳到靠后那个标签的页面，要自己 scrollIntoView（见整机详情页）。 */
  .pcr-touch-tabs .el-tabs__nav-wrap.is-scrollable { padding: 0; }
  .pcr-touch-tabs .el-tabs__nav-prev,
  .pcr-touch-tabs .el-tabs__nav-next { display: none; }
  .pcr-touch-tabs .el-tabs__nav-scroll {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .pcr-touch-tabs .el-tabs__nav-scroll::-webkit-scrollbar { display: none; }
  .pcr-touch-tabs .el-tabs__nav { transform: none !important; }
  .pcr-touch-tabs .el-tabs__item { height: 44px; }
}
@media (max-width: 768px) {
  .pcr-touch-tabs .el-tabs__item { padding: 0 12px; }
}

/* 通用工具类 */
.pcr-profit { color: var(--pcr-profit); }
.pcr-loss { color: var(--pcr-loss); }
.pcr-dim { color: var(--pcr-text-dim); }
.pcr-mono { font-variant-numeric: tabular-nums; }
</style>
