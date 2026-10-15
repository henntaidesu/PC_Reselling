<template>
  <!-- 详情弹窗的骨架，显卡与整机共用。版式照 FreeMarket_Manager 库存管理的商品表单：
       顶栏（名称 / 总账药丸 / 自动保存 / 关闭）+ 左边一摞分区卡片 + 右边定宽图片侧栏。
       没有模块导航——字段能平铺就平铺，只有真正次要的内容（资金明细、记录、部件编辑）
       才收进左列最下面那张标签页卡。
       整个骨架是**定高**的（高度由弹窗给，见 App.vue 的 .pcr-detail-dialog），弹窗本身不滚：
       上面几张卡按内容高，标签页卡（.pd-tabs-card）吃掉剩下的高度、在卡里滚。
       卡片、徽章、紧凑表单这些类是全局的（App.vue 的 .pd-*）：它们写在页面传进来的
       插槽内容里，放在这里的 scoped 样式够不着。 -->
  <div class="shell" v-loading="loading">
    <header class="shell-head">
      <div class="shell-title"><slot name="title" /></div>
      <div v-if="$slots.stats" class="shell-stats"><slot name="stats" /></div>
      <div class="shell-head-right">
        <slot name="actions" />
        <el-button :icon="Close" text class="shell-close" :title="t('common.close')" @click="emit('close')" />
      </div>
    </header>

    <div v-if="ready" class="shell-body">
      <div class="shell-main"><slot /></div>
      <aside v-if="$slots.aside" class="shell-aside"><slot name="aside" /></aside>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { Close } from '@element-plus/icons-vue'

defineProps({
  loading: { type: Boolean, default: false },
  // 数据到了才摆主体：卡片里的控件全绑在 form 上，空壳先摆出来只会闪一下空表单
  ready: { type: Boolean, default: false }
})
const emit = defineEmits(['close'])
const { t } = useI18n()
</script>

<style scoped>
.shell {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
  /* 控件统一 small，但抬到 30px：再矮就点不准了 */
  --el-component-size-small: 30px;
}

.shell-head {
  flex: none;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 16px;
  padding: 10px 12px 10px 18px;
  border-bottom: 1px solid var(--pcr-border);
}
.shell-title { flex: 0 1 auto; min-width: 0; display: flex; align-items: center; gap: 10px; }
.shell-stats { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
.shell-head-right { margin-left: auto; flex: none; display: flex; align-items: center; gap: 8px; }
.shell-close { font-size: 18px; }

.shell-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  gap: 12px;
  padding: 12px 14px 14px;
}
.shell-main {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
/* 图片侧栏：定宽、与左列等高，图多了自己滚，不把弹窗撑高 */
.shell-aside {
  flex: 0 0 280px;
  width: 280px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 8px 12px 12px;
  border: 1px solid var(--pcr-border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  overflow-y: auto;
}

/* 平板竖屏（紧凑宽度）：侧栏收窄，给左边的字段多留地方 */
@media (min-width: 769px) and (max-width: 1200px) {
  .shell-aside { flex-basis: 220px; width: 220px; }
}

/* 手机：全屏弹窗。卡片和侧栏上下叠放，整块一起滚——这是唯一退回滚动的地方；
   顶栏钉住，关闭按钮始终够得着 */
@media (max-width: 768px) {
  .shell { overflow-y: auto; -webkit-overflow-scrolling: touch; }
  .shell-head {
    position: sticky;
    top: 0;
    z-index: 5;
    background: var(--el-dialog-bg-color, var(--el-bg-color));
    padding: calc(8px + env(safe-area-inset-top, 0px)) 8px 8px 12px;
  }
  .shell-stats { order: 3; width: 100%; }
  .shell-body { flex: none; flex-direction: column; padding: 10px 10px calc(16px + env(safe-area-inset-bottom, 0px)); }
  .shell-main { flex: none; }
  .shell-aside { flex: none; width: 100%; overflow: visible; }
}
</style>
