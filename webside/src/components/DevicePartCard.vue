<template>
  <div class="part-card" :class="{ 'part-card--blank': blank }">
    <div class="part-head">
      <el-tag size="small" effect="plain" type="info" class="head-tag">{{ t('partType.' + part.part_type) }}</el-tag>
      <!-- 「未填写 / 未出售 / 售价」紧跟类型标签，排在名称**左边**：这一列是等宽对齐的，
           跟在长短不一的名称后面会左右乱跳，一眼扫不出哪几件还没卖掉 -->
      <el-tag v-if="blank" size="small" type="info" effect="plain" class="head-tag">{{ t('device.blankSlot') }}</el-tag>
      <el-tag v-else-if="sold" size="small" type="success" effect="plain" class="head-tag">
        {{ formatMoney(part.sale_amount, part.sale_currency) }}
      </el-tag>
      <el-tag v-else size="small" type="info" effect="plain" class="head-tag">{{ t('device.unsold') }}</el-tag>
      <span class="part-title">{{ title }}</span>
      <span v-if="net !== null" class="pcr-dim part-net">
        {{ t('device.netIncome') }} <b class="pcr-mono">{{ cny(net) }}</b>
      </span>
      <div class="part-actions">
        <el-button size="small" text @click="expanded = !expanded">
          {{ expanded ? '−' : '+' }} {{ t('card.note') }} / {{ t('card.media') }}
          <span v-if="part._media_count" class="media-badge">{{ part._media_count }}</span>
        </el-button>
        <el-button size="small" text type="danger" :icon="Delete" :title="t('device.removePart')"
          @click="emit('remove')" />
      </div>
    </div>

    <div class="part-fields">
      <InlineField :label="t('card.brand')">
        <!-- 品牌候选按部件类型给：CPU 只有 Intel / AMD（不允许现场新建），显卡直接用
             系统里的品牌字典，其余给一份常见清单但可以现场输入 -->
        <el-select v-model="part.brand" filterable :allow-create="!schema.brandStrict"
          default-first-option clearable :placeholder="t('common.unset')">
          <el-option v-for="b in brandOptions" :key="b" :label="b" :value="b" />
        </el-select>
      </InlineField>
      <InlineField :label="t('card.model')">
        <el-select v-if="modelOptions.length" v-model="part.model" filterable allow-create
          default-first-option clearable :placeholder="t('common.unset')">
          <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
        </el-select>
        <el-input v-else v-model="part.model" :placeholder="t('common.unset')" />
      </InlineField>
      <!-- 「规格」这一栏各类型填的不是一回事（显存 / 容量 / 功率 / 芯片组），标题跟着类型走 -->
      <InlineField :label="t(specLabelKey(part.part_type))">
        <el-input v-model="part.spec" :placeholder="t('common.unset')" />
      </InlineField>
      <InlineField :label="t('card.serialNo')">
        <el-input v-model="part.serial_no" class="mono-input" :placeholder="t('common.unset')" />
      </InlineField>

      <InlineField :label="t('card.saleDate')">
        <el-date-picker v-model="part.sale_date" type="date" value-format="YYYY-MM-DD"
          :placeholder="t('common.unset')" />
      </InlineField>
      <InlineField :label="t('card.saleAmount')">
        <MoneyInput v-model:amount="part.sale_amount" v-model:currency="part.sale_currency" />
      </InlineField>
      <InlineField :label="t('card.domesticShipping')">
        <MoneyInput v-model:amount="part.domestic_shipping_amount"
          v-model:currency="part.domestic_shipping_currency" />
      </InlineField>
      <InlineField :label="t('card.status')">
        <el-select v-model="part.status">
          <el-option v-for="s in statuses" :key="s" :label="t('status.' + s)" :value="s" />
        </el-select>
      </InlineField>
    </div>

    <!-- 备注与图片折叠着放：一台机器十来个部件，全展开的话页面长得没法用。
         抬头上的角标显示已有几张图，折叠时也看得见。 -->
    <div v-if="expanded" class="part-more">
      <InlineField :label="t('card.note')" stack>
        <el-input v-model="part.note" :placeholder="t('common.unset')" />
      </InlineField>
      <div class="media-label">{{ t('device.partMedia') }}</div>
      <PartMediaGallery
        :part-id="part.id"
        :hosting-configured="hostingConfigured"
        @changed="(n) => emit('media-changed', n)"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Delete } from '@element-plus/icons-vue'
import { cny, formatMoney } from '@/utils/format'
import { isBlankPart, partSchema, specLabelKey } from '@/constants/parts'
import { useMetaStore } from '@/stores/meta'
import InlineField from './InlineField.vue'
import MoneyInput from './MoneyInput.vue'
import PartMediaGallery from './PartMediaGallery.vue'

// 这里**直接改 part 上的字段**（v-model="part.brand"）。part 就是详情页 form.parts
// 里的那个对象，改它正是目的：页面的深层 watch 会看到，600ms 后自动落盘。若改成
// 逐字段 emit 回去，十来个字段 × 每个都要一条事件，除了噪音没有任何好处。
const props = defineProps({
  part: { type: Object, required: true },
  // 这个部件折人民币后的净收入，由页面从上次保存的返回值里按 id 取
  net: { type: Number, default: null },
  hostingConfigured: { type: Boolean, default: true }
})
const emit = defineEmits(['remove', 'media-changed'])

const { t } = useI18n()
const meta = useMetaStore()

const expanded = ref(false)
const statuses = computed(() => meta.enums.statuses || [])
const schema = computed(() => partSchema(props.part.part_type))

const brandOptions = computed(() => {
  if (props.part.part_type === 'gpu') {
    // 显卡用系统里维护的品牌字典（「系统配置 → 品牌/型号」那份），空了才退回内置清单
    const dict = meta.brands.map((b) => b.name).filter(Boolean)
    if (dict.length) return dict
  }
  return schema.value.brands
})
// 显卡的型号同样取字典；其余类型型号太发散，手填
const modelOptions = computed(() =>
  props.part.part_type === 'gpu' ? meta.models.map((m) => m.name) : []
)

// 「没填过的槽位」的判断与详情页共用同一份（见 constants/parts.js）：这里画淡一档，
// 那边据此决定提交不提交，两边一旦不一致，部件就会莫名其妙地多出来或者消失
const blank = computed(() => isBlankPart(props.part))
const sold = computed(() => {
  const v = props.part.sale_amount
  return v !== null && v !== undefined && v !== ''
})
const title = computed(() =>
  [props.part.brand, props.part.model, props.part.spec].filter(Boolean).join(' ') || '—'
)
</script>

<style scoped>
.part-card {
  border: 1px solid #22304a;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
  background: rgba(91, 140, 255, 0.04);
}
/* 还没填的槽位淡一点：一眼能看出哪些是待填的模板、哪些是真有的部件 */
.part-card--blank { border-style: dashed; background: transparent; }
.part-card--blank .part-head { opacity: 0.75; }
.part-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 4px; }
.part-title { font-size: 13px; color: #c7d0de; }
.head-tag { flex: 0 0 auto; }
.part-net { font-size: 12px; }
.part-actions { margin-left: auto; display: flex; align-items: center; gap: 2px; }
.media-badge {
  margin-left: 4px;
  padding: 0 5px;
  border-radius: 8px;
  background: #5b8cff;
  color: #fff;
  font-size: 11px;
}
/* 部件字段两列排：一台机器十来个部件，一行一个字段的话整页要划很久 */
.part-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}
.part-more { margin-top: 6px; padding-top: 6px; border-top: 1px solid #1c2740; }
.media-label { font-size: 12px; color: #9aa6b8; margin: 6px 0 4px; }
.mono-input :deep(.el-input__inner) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }

@media (max-width: 900px) {
  .part-fields { grid-template-columns: minmax(0, 1fr); }
  .part-actions { margin-left: 0; }
}
</style>
