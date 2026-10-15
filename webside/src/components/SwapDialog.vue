<template>
  <!-- 实物置换：一张单卡 ↔ 某台整机里的一个显卡部件。显卡详情和整机详情都从这里发起，
       区别只在「自己是哪一头、去挑另一头」。换的只是实物信息（品牌 / 型号 / 核心编号 /
       序列号 / 图片），两边的价格、资金、归属人、状态都不动（规则见后端 src/swaps.py）。 -->
  <el-dialog :model-value="modelValue" :title="t('swap.title')" width="min(680px, 94vw)" align-center
    append-to-body @update:model-value="(v) => emit('update:modelValue', v)" @open="onOpen">
    <p class="pd-note sw-hint">{{ t('swap.hint') }}</p>

    <div class="sw-self">
      <span class="sw-k">{{ t('swap.self') }}</span>
      <span class="sw-v">{{ describe(source) }}</span>
    </div>

    <div class="sw-k sw-pick-label">{{ mode === 'card' ? t('swap.pickPart') : t('swap.pickCard') }}</div>
    <div v-loading="loading" class="sw-list">
      <button v-for="c in candidates" :key="keyOf(c)" type="button" class="sw-row"
        :class="{ 'is-active': keyOf(c) === picked }" @click="picked = keyOf(c)">
        <span class="sw-main">
          <b>{{ [c.brand, c.model].filter(Boolean).join(' ') || '—' }}</b>
          <span class="pcr-dim pcr-mono sw-ids">
            <template v-if="c.core_no">{{ t('card.coreNo') }} {{ c.core_no }}</template>
            <template v-if="c.serial_no"> · SN {{ c.serial_no }}</template>
          </span>
        </span>
        <span class="sw-where pcr-dim">
          <span class="pcr-mono">{{ mode === 'card' ? c.device_mgmt_no : c.mgmt_no }}</span>
          <template v-if="mode === 'card' && c.device_title"> · {{ c.device_title }}</template>
        </span>
        <el-tag v-if="c.owner" size="small" effect="dark" type="info">{{ c.owner }}</el-tag>
        <StatusTag :status="c.status" />
      </button>
      <el-empty v-if="!loading && !candidates.length" :description="t('swap.noCandidates')" :image-size="50" />
    </div>

    <el-form label-position="top" size="small" class="pd-form sw-form" @submit.prevent>
      <el-form-item :label="t('swap.date')">
        <el-date-picker v-model="swapDate" type="date" value-format="YYYY-MM-DD" :editable="!isTouch" :clearable="false" />
      </el-form-item>
      <el-form-item :label="t('card.note')" class="sw-note">
        <el-input v-model="note" maxlength="500" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :disabled="!picked" :loading="busy" @click="submit">{{ t('swap.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessageBox } from 'element-plus'
import { swapsApi } from '@/api'
import { ElMessage } from '@/utils/notify'
import { useIsTouch } from '@/composables/useIsMobile'
import StatusTag from './StatusTag.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  // 'card' = 从显卡发起（挑整机里的显卡部件）；'part' = 从部件发起（挑单卡）
  mode: { type: String, required: true },
  sourceId: { type: Number, default: null },
  // 自己这一头的实物信息，只用于对照显示：{ brand, model, core_no, serial_no, owner }
  source: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['update:modelValue', 'done'])
const { t } = useI18n()
const { isTouch } = useIsTouch()

const candidates = ref([])
const loading = ref(false)
const picked = ref(null)
const swapDate = ref(null)
const note = ref('')
const busy = ref(false)

const keyOf = (c) => (props.mode === 'card' ? c.part_id : c.card_id)

function describe(x) {
  if (!x) return ''
  const name = [x.brand, x.model].filter(Boolean).join(' ') || '—'
  const ids = [x.core_no && `${t('card.coreNo')} ${x.core_no}`, x.serial_no && `SN ${x.serial_no}`]
  return [name, ...ids.filter(Boolean)].join(' · ') + (x.owner ? `（${x.owner}）` : '')
}

function today() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// 每次打开都重拉候选：上一次打开之后别的卡可能已经卖掉或换过了
async function onOpen() {
  picked.value = null
  note.value = ''
  swapDate.value = today()
  candidates.value = []
  loading.value = true
  try {
    const params = props.mode === 'card' ? { card_id: props.sourceId } : { part_id: props.sourceId }
    const res = await swapsApi.candidates(params)
    candidates.value = res.items || []
  } catch { /* 拦截器已提示 */ } finally {
    loading.value = false
  }
}

async function submit() {
  const target = candidates.value.find((c) => keyOf(c) === picked.value)
  if (!target) return
  // 互换之后两边的序列号、照片都换了位置，点错了得再换一次才回得来——问一声
  try {
    await ElMessageBox.confirm(
      t('swap.confirmText', { a: describe(props.source), b: describe(target) }),
      t('swap.title'), { type: 'warning' })
  } catch {
    return
  }
  busy.value = true
  try {
    await swapsApi.create({
      card_id: props.mode === 'card' ? props.sourceId : target.card_id,
      part_id: props.mode === 'card' ? target.part_id : props.sourceId,
      swap_date: swapDate.value,
      note: note.value || null
    })
    ElMessage.success(t('swap.done'))
    emit('update:modelValue', false)
    emit('done')
  } catch { /* 拦截器已提示 */ } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.sw-hint { margin: 0 0 10px; }
.sw-self { display: flex; gap: 8px; align-items: baseline; padding: 8px 10px; border-radius: 7px; background: rgba(91, 140, 255, 0.08); }
.sw-k { color: #8a94a6; font-size: 12px; flex: none; }
.sw-v { color: #e6edf7; font-size: 13px; }
.sw-pick-label { margin: 12px 0 6px; }
.sw-list { display: flex; flex-direction: column; gap: 4px; max-height: 42vh; overflow-y: auto; min-height: 60px; }
.sw-row {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  width: 100%; padding: 7px 10px; border: 1px solid transparent; border-radius: 7px;
  background: rgba(255, 255, 255, 0.02); color: inherit; font-size: 13px; text-align: left; cursor: pointer;
}
.sw-row:hover { background: rgba(91, 140, 255, 0.06); }
.sw-row.is-active { border-color: rgba(91, 140, 255, 0.6); background: rgba(91, 140, 255, 0.12); }
.sw-main { flex: 1 1 220px; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.sw-main b { color: #e6edf7; font-weight: 500; }
.sw-ids { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sw-where { font-size: 12px; }
.sw-form { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
.sw-note { flex: 1 1 220px; }
@media (hover: none) {
  .sw-row { min-height: 44px; }
}
</style>
