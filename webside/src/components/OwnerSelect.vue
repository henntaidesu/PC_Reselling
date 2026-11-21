<template>
  <!-- 归属人 / 出资人下拉：显卡、整机、部件、资金池的注资与支出共用。候选就是用户系统里的
       账号（meta.people），值是用户 id——改名不影响已经选上的（见后端 src/people.py）。
       不能现敲新名字：人要先在「系统配置 → 用户」里建好。
       清空 = 未指定；部件上清空 = 跟随整机，由调用方用 placeholder 说清楚是谁。 -->
  <el-select :model-value="modelValue" filterable clearable
    :placeholder="placeholder || t('owner.none')" @update:model-value="onPick">
    <el-option v-for="p in options" :key="p.id" :label="p.name" :value="p.id">
      <span>{{ p.name }}</span>
      <span v-if="!p.is_active" class="pcr-dim os-sub">{{ t('users.disabled') }}</span>
      <span v-else-if="p.username !== p.name" class="pcr-dim os-sub pcr-mono">{{ p.username }}</span>
    </el-option>
  </el-select>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMetaStore } from '@/stores/meta'

const props = defineProps({
  modelValue: { type: Number, default: null },
  placeholder: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()
const meta = useMetaStore()

// 只列启用的人；当前选中的若已停用也留着，否则输入框里显示的是一个裸 id
const options = computed(() =>
  meta.people.filter((p) => p.is_active || p.id === props.modelValue))

// 清空时 el-select 给的是空串或 undefined，统一成 null：「没填」只该有一种形态
function onPick(value) {
  emit('update:modelValue', value || null)
}
</script>

<style scoped>
.os-sub { float: right; margin-left: 12px; font-size: 12px; }
</style>
