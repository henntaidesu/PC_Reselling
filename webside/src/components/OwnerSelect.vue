<template>
  <!-- 归属人下拉：显卡、整机、部件三处共用。候选就是出资人那一份名单（meta.contributors），
       可以现敲新名字——后端存的时候顺手落进字典（funds.ensure_contributor），这里存完刷新候选。
       清空 = 未指定；部件上清空 = 跟随整机，由调用方用 placeholder 说清楚是谁。 -->
  <el-select :model-value="modelValue" filterable allow-create default-first-option clearable
    :placeholder="placeholder || t('owner.none')" @update:model-value="onPick">
    <el-option v-for="name in meta.contributors" :key="name" :label="name" :value="name" />
  </el-select>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import { useMetaStore } from '@/stores/meta'

defineProps({
  modelValue: { type: String, default: null },
  placeholder: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()
const meta = useMetaStore()

// 清空时 el-select 给的是空串，统一成 null：「没填」只该有一种形态
function onPick(value) {
  emit('update:modelValue', (value || '').trim() || null)
}
</script>
