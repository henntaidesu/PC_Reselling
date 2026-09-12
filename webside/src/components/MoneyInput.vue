<template>
  <!-- 金额 + 币种。两者必须在一起：一个「390000」不说清是日元还是人民币，
       后面每一步换算都是错的。标签由外面的 InlineField 给，这里只出控件。 -->
  <div class="money-input">
    <el-input-number
      :model-value="amount"
      :precision="currency === 'JPY' ? 0 : 2"
      :step="currency === 'JPY' ? 100 : 1"
      :min="0"
      :controls="false"
      :placeholder="placeholder"
      class="amount"
      @update:model-value="(v) => emit('update:amount', v)"
    />
    <el-select
      :model-value="currency"
      class="currency"
      @update:model-value="(v) => emit('update:currency', v)"
    >
      <el-option v-for="c in currencies" :key="c" :label="t('currency.' + c + '_short')" :value="c" />
    </el-select>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMetaStore } from '@/stores/meta'

defineProps({
  amount: { type: [Number, null], default: null },
  currency: { type: String, default: 'JPY' },
  placeholder: { type: String, default: '' }
})
const emit = defineEmits(['update:amount', 'update:currency'])

const { t } = useI18n()
const meta = useMetaStore()
const currencies = computed(() => meta.enums.currencies?.length ? meta.enums.currencies : ['JPY', 'CNY'])
</script>

<style scoped>
.money-input { display: flex; gap: 4px; width: 100%; align-items: center; }
.amount { flex: 1 1 auto; min-width: 0; }
.amount :deep(.el-input__inner) { text-align: right; }
/* 币种这一格定宽。用 flex-basis 而不是 width：外面的 InlineField 会把所有控件
   刷成 width:100% !important，只有 flex-basis 压得住它 */
.currency { flex: 0 0 74px; }
.currency :deep(.el-select__wrapper) { padding-left: 4px; padding-right: 4px; }
.currency :deep(.el-select__selection) { justify-content: flex-end; }
.money-input :deep(.el-input-number) { width: 100% !important; }
</style>
