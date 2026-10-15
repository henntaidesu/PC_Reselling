<template>
  <!-- 「这件货的钱由谁出、各占多少」。显卡和整机是同一件事，所以同一个组件，
       别在两个详情页里各画一遍——比例的校验规则写两份，迟早只改其中一份。 -->
  <div class="fund-shares">
    <div v-for="(row, idx) in rows" :key="idx" class="row">
      <el-select v-model="rows[idx].name" filterable allow-create default-first-option
        class="name-select" :placeholder="t('fundShare.placeholder')" @change="onNameChange(idx)">
        <el-option v-for="opt in availableOptions(idx)" :key="opt" :label="opt" :value="opt" />
      </el-select>
      <template v-if="rows.length > 1">
        <el-input-number v-model="rows[idx].pct" :min="0" :max="100" :precision="2" :step="5"
          :controls="false" size="small" inputmode="decimal" class="pct" @change="publish" />
        <span class="unit">%</span>
      </template>
      <el-button v-if="rows.length > 1" :icon="Minus" circle size="small"
        class="remove-btn" @click="removeRow(idx)" />
    </div>
    <div class="actions">
      <el-button :icon="Plus" circle size="small" @click="addRow" />
      <template v-if="rows.length > 1">
        <span class="sum" :class="{ bad: !sumOk }">{{ t('fundShare.sum', { n: shownSum }) }}</span>
        <el-button link type="primary" size="small" @click="distributeEvenly">
          {{ t('fundShare.even') }}
        </el-button>
      </template>
    </div>
    <div v-if="rows.length > 1 && !sumOk" class="warn">{{ t('fundShare.sumWarn') }}</div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, Minus } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()

const rows = ref([{ name: '', pct: 100 }])
let syncing = false

const sum = computed(() => rows.value.reduce((acc, r) => acc + (Number(r.pct) || 0), 0))
const shownSum = computed(() => Math.round(sum.value * 100) / 100)
const sumOk = computed(() => Math.abs(sum.value - 100) <= 0.01)

watch(() => props.modelValue, (val) => {
  syncing = true
  if (val && val.length) {
    rows.value = val.map(s => ({ name: s.contributor, pct: Number(s.share_pct) }))
  } else {
    rows.value = [{ name: '', pct: 100 }]
  }
  syncing = false
}, { immediate: true, deep: true })

function availableOptions(idx) {
  const used = rows.value.map(r => r.name).filter((n, i) => i !== idx && n)
  return props.options.filter(n => !used.includes(n))
}

function onNameChange(idx) {
  const name = rows.value[idx].name
  if (rows.value.filter((r, i) => i !== idx && r.name === name).length) {
    rows.value[idx].name = ''
    return
  }
  publish()
}

function addRow() {
  rows.value.push({ name: '', pct: 0 })
  if (rows.value.length === 2) distributeEvenly()
}

function removeRow(idx) {
  rows.value.splice(idx, 1)
  if (rows.value.length === 1) {
    rows.value[0].pct = 100
  } else {
    distributeEvenly()
  }
  publish()
}

function distributeEvenly() {
  const n = rows.value.length
  if (n > 1) {
    const each = Math.floor(10000 / n) / 100
    rows.value.forEach((row, i) => {
      row.pct = i === n - 1 ? Math.round((100 - each * (n - 1)) * 100) / 100 : each
    })
  }
  publish()
}

function publish() {
  if (syncing) return
  const valid = rows.value.filter(r => r.name)
  if (!valid.length) { emit('update:modelValue', []); return }
  if (valid.length === 1) {
    emit('update:modelValue', [{ contributor: valid[0].name, share_pct: 100 }])
    return
  }
  if (!sumOk.value) return
  emit('update:modelValue', valid.map(r => ({
    contributor: r.name,
    share_pct: Number(r.pct) || 0
  })))
}
</script>

<style scoped>
.fund-shares { width: 100%; }
.row { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.name-select { flex: 1; min-width: 0; }
.pct { width: 92px; }
.unit { font-size: 12px; color: #9aa6b8; }
.remove-btn { flex-shrink: 0; }
.actions { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.sum { font-size: 12px; color: #9aa6b8; }
.sum.bad { color: #e6a23c; }
.warn { font-size: 12px; color: #e6a23c; line-height: 1.5; margin-top: 2px; }

@media (hover: none) {
  .row { padding: 4px 0; }
  /* small 圆按钮 24px，「+ / −」两个挨着比例框，手指按不准 */
  .remove-btn, .actions :deep(.el-button.is-circle) { width: 32px; height: 32px; }
  .actions :deep(.el-button.is-link) { padding: 8px 4px; }
  .pct { width: 110px; }
}
</style>
