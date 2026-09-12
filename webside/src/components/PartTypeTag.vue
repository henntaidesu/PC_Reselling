<template>
  <!-- 部件类型标签。颜色只有 utils/format.js 那一份，库存列表的二级行与整机详情里的
       部件一览表共用这一个组件——两处显示同一种东西，颜色对不上比没有颜色更糟。 -->
  <el-tag size="small" effect="plain" :style="tagStyle">{{ t('partType.' + type) }}</el-tag>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { partTypeColor } from '@/utils/format'

const props = defineProps({ type: { type: String, required: true } })
const { t } = useI18n()

// 描边样式：底透明、字与边框都用类型色。实心的话十来行部件会糊成一片色块，
// 而这一列只是给行分类，不该比行里的金额更抢眼。
const tagStyle = computed(() => {
  const color = partTypeColor(props.type)
  return {
    '--el-tag-bg-color': 'transparent',
    '--el-tag-border-color': color,
    '--el-tag-text-color': color
  }
})
</script>
