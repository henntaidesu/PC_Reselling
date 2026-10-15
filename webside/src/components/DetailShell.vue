<template>
  <!-- 详情弹窗的骨架：顶栏 / 摘要条 / 左侧模块导航 + 右侧模块页。显卡与整机共用。
       整个骨架是**定高**的（高度由弹窗给，见 App.vue 的 .pcr-detail-dialog），
       弹窗本身永远不出现滚动条：内容按模块拆开，一次只摆一个模块，每个模块都按
       「一屏放得下」来排。模块区留一个 overflow: auto 只是兜底（窄屏、图片特别多），
       不是常态。 -->
  <div class="shell" v-loading="loading">
    <header class="shell-head">
      <div class="shell-title"><slot name="title" /></div>
      <div class="shell-head-right">
        <slot name="actions" />
        <el-button :icon="Close" text class="shell-close" :title="t('common.close')" @click="emit('close')" />
      </div>
    </header>

    <!-- 摘要条：切到哪个模块都看得见这件货的总账——改售价的时候得对着成本看 -->
    <div v-if="$slots.summary" class="shell-summary"><slot name="summary" /></div>

    <div class="shell-body">
      <!-- 原生 button：键盘能 Tab 到、回车能按，当前项用 aria-current 标出来 -->
      <nav class="shell-nav">
        <button
          v-for="m in modules"
          :key="m.key"
          type="button"
          class="shell-nav-item"
          :class="{ 'is-active': m.key === modelValue }"
          :aria-current="m.key === modelValue ? 'page' : undefined"
          @click="emit('update:modelValue', m.key)"
        >
          <el-icon v-if="m.icon" class="shell-nav-icon"><component :is="m.icon" /></el-icon>
          <span class="shell-nav-label">{{ m.label }}</span>
          <span v-if="m.badge" class="shell-nav-badge pcr-mono">{{ m.badge }}</span>
        </button>
      </nav>
      <section class="shell-pane">
        <slot />
      </section>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { Close } from '@element-plus/icons-vue'

// 模块：[{ key, label, icon?, badge? }]。badge 是导航上的小角标（图片数、部件数），
// 0 / 空不显示——「0」在导航里只会让人以为这一页有东西要看。
defineProps({
  modules: { type: Array, required: true },
  modelValue: { type: String, required: true },
  loading: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'close'])
const { t } = useI18n()
</script>

<style scoped>
.shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.shell-head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px 12px 20px;
  border-bottom: 1px solid var(--pcr-border);
}
.shell-title {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.shell-head-right { flex: none; display: flex; align-items: center; gap: 8px; }
.shell-close { font-size: 18px; }

.shell-summary {
  flex: none;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 28px;
  padding: 10px 20px;
  border-bottom: 1px solid var(--pcr-border);
  background: rgba(255, 255, 255, 0.015);
}

.shell-body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr);
}
.shell-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 8px;
  border-right: 1px solid var(--pcr-border);
  overflow-y: auto;
}
.shell-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #a6b0c2;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}
.shell-nav-item:hover { background: rgba(255, 255, 255, 0.04); color: #e6edf7; }
.shell-nav-item:focus-visible { outline: 2px solid var(--pcr-accent); outline-offset: -2px; }
/* 当前项与侧栏菜单的选中态同一种渐变，一眼认得出是「现在在这儿」 */
.shell-nav-item.is-active {
  background: linear-gradient(90deg, rgba(91, 140, 255, 0.22), rgba(124, 92, 255, 0.12));
  color: #fff;
}
.shell-nav-icon { font-size: 16px; flex: none; }
.shell-nav-label { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shell-nav-badge {
  flex: none;
  min-width: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: rgba(91, 140, 255, 0.18);
  color: #8fb8ff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.shell-pane {
  min-width: 0;
  min-height: 0;
  padding: 18px 22px;
  overflow: auto;
}

/* 手机：左侧导航换成顶上一条横滑的标签。168px 的竖栏在 360px 的屏上要吃掉一半宽度。
   这一档模块页本身放不下一屏（字段只能排一列），由模块区自己滚——这是窄屏上唯一
   退回滚动的地方，导航和顶栏仍然钉着不动。 */
@media (max-width: 768px) {
  .shell-head { padding: calc(8px + env(safe-area-inset-top, 0px)) 8px 8px 12px; }
  .shell-summary { gap: 6px 18px; padding: 8px 12px; }
  .shell-body { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); }
  .shell-nav {
    flex-direction: row;
    gap: 4px;
    padding: 8px 10px;
    border-right: none;
    border-bottom: 1px solid var(--pcr-border);
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }
  .shell-nav::-webkit-scrollbar { display: none; }
  .shell-nav-item { width: auto; flex: none; padding: 8px 12px; }
  .shell-nav-label { overflow: visible; }
  .shell-pane { padding: 14px 12px calc(16px + env(safe-area-inset-bottom, 0px)); }
}
</style>
