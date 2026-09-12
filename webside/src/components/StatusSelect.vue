<template>
  <!-- 状态下拉。选项与选中项都带状态色的矩形底色，颜色取 format.js 的那一份，
       和列表标签、时间轴圆点是同一套——下拉里是什么色，选完在列表里还是什么色。
       矩形而不是列表里那种圆角胶囊：下拉是一列等宽的块，圆角排在一起会显得散。
       四处状态下拉（显卡详情 / 整机详情 / 部件面板 / 库存筛选）共用这一份，
       别再在各页面里写 v-for el-option：加状态时漏掉一处就只有那里是白底文字。 -->
  <el-select
    :model-value="modelValue"
    :multiple="multiple"
    popper-class="status-select-dropdown"
    @update:model-value="(v) => emit('update:modelValue', v)"
  >
    <!-- 单选才接管选中项：多选时 el-select 把选中项塞进它自己的 el-tag 里，
         再放一个标签就成了标签套标签，那种情况维持默认文字 -->
    <template v-if="!multiple" #label="{ value }">
      <StatusTag :status="value" :round="false" />
    </template>
    <el-option v-for="s in statuses" :key="s" :label="t('status.' + s)" :value="s">
      <StatusTag :status="s" :round="false" class="opt-tag" />
    </el-option>
  </el-select>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMetaStore } from '@/stores/meta'
import StatusTag from './StatusTag.vue'

defineProps({
  modelValue: { type: [String, Array, null], default: null },
  multiple: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()
const meta = useMetaStore()
// 取值与顺序都由后端 /options/enums 给，前端不另存一份状态列表
const statuses = computed(() => meta.enums.statuses || [])
</script>

<style scoped>
/* 选项里的色块定宽：长短不一的矩形排成一列会参差不齐，等宽才看得出这是一张色卡 */
.opt-tag { min-width: 88px; }
</style>

<style>
/* 下拉浮层挂在 body 上，scoped 够不着，只能靠 popper-class 圈住范围 */
/* 默认左内边距是给纯文字留的，色块自己带内边距，再留那么多整行会偏右 */
.status-select-dropdown .el-select-dropdown__item { padding-left: 12px; }
/* 选中项原本靠文字变蓝来标，而文字现在盖在色块里、颜色是状态色，那条线索没了，
   改成整行淡底 + 左侧一道亮条 */
.status-select-dropdown .el-select-dropdown__item.is-selected {
  background: rgba(91, 140, 255, .16);
  box-shadow: inset 3px 0 0 var(--pcr-accent);
}
</style>
