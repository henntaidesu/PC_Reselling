<template>
  <el-row :gutter="16">
    <el-col :xs="24" :lg="14">
      <el-card shadow="never" class="panel-card">
        <template #header>
          <div class="panel-head">
            <el-tag size="small" effect="plain" type="info">{{ t('partType.' + part.part_type) }}</el-tag>
            <el-tag v-if="blank" size="small" type="info" effect="plain">{{ t('device.blankSlot') }}</el-tag>
            <el-tag v-else-if="sold" size="small" type="success" effect="plain">
              {{ formatMoney(part.sale_amount, part.sale_currency) }}
            </el-tag>
            <el-tag v-else size="small" type="info" effect="plain">{{ t('device.unsold') }}</el-tag>
            <span class="panel-title">{{ title }}</span>
            <span v-if="net !== null" class="pcr-dim panel-net">
              {{ t('device.netIncome') }} <b class="pcr-mono">{{ cny(net) }}</b>
            </span>
            <el-button class="panel-del" size="small" text type="danger" :icon="Delete"
              @click="emit('remove')">
              {{ t('device.removePart') }}
            </el-button>
          </div>
        </template>

        <div class="fields">
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
        </div>

        <el-divider />

        <div class="fields">
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

        <el-divider />

        <InlineField :label="t('card.note')" stack>
          <el-input v-model="part.note" type="textarea" :rows="2" :placeholder="t('common.unset')" />
        </InlineField>
      </el-card>
    </el-col>

    <el-col :xs="24" :lg="10">
      <el-card shadow="never" class="panel-card">
        <template #header>
          {{ t('device.partMedia') }}
          <span v-if="part._media_count" class="pcr-dim count">{{ part._media_count }}</span>
        </template>
        <!-- 图片区一直在，空槽位也能直接传：要传的那一刻页面会先把这一行存出来拿到 id
             （ensureId），而不是要求用户先填点什么 -->
        <MediaGallery
          owner="parts"
          :owner-id="part.id"
          :ensure-id="ensureId"
          :hosting-configured="hostingConfigured"
          @changed="(n) => emit('media-changed', n)"
        />
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Delete } from '@element-plus/icons-vue'
import { cny, formatMoney } from '@/utils/format'
import { hasPartContent, partSchema, specLabelKey } from '@/constants/parts'
import { useMetaStore } from '@/stores/meta'
import InlineField from './InlineField.vue'
import MediaGallery from './MediaGallery.vue'
import MoneyInput from './MoneyInput.vue'

// 这里**直接改 part 上的字段**（v-model="part.brand"）。part 就是详情页 form.parts
// 里的那个对象，改它正是目的：页面的深层 watch 会看到，600ms 后自动落盘。若改成
// 逐字段 emit 回去，十来个字段 × 每个都要一条事件，除了噪音没有任何好处。
const props = defineProps({
  part: { type: Object, required: true },
  // 这个部件折人民币后的净收入，由页面从上次保存的返回值里按 id 取
  net: { type: Number, default: null },
  // 上传图片前把这一行落盘并返回它的 id，由详情页提供
  ensureId: { type: Function, default: null },
  hostingConfigured: { type: Boolean, default: true }
})
const emit = defineEmits(['remove', 'media-changed'])

const { t } = useI18n()
const meta = useMetaStore()

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

// 标「未填写」看的是**有没有内容**，不是「要不要提交」——从服务端载入的行即使字段
// 全空也仍然存在（见 constants/parts.js 里两个函数的分工）
const blank = computed(() => !hasPartContent(props.part))
const sold = computed(() => {
  const v = props.part.sale_amount
  return v !== null && v !== undefined && v !== ''
})
const title = computed(() =>
  [props.part.brand, props.part.model, props.part.spec].filter(Boolean).join(' ') || '—'
)
</script>

<style scoped>
.panel-card { margin-bottom: 16px; }
.panel-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.panel-title { font-size: 14px; color: #e6edf7; }
.panel-net { font-size: 12px; }
.panel-del { margin-left: auto; }
.count { font-size: 12px; margin-left: 4px; }
/* 字段两列排，窄屏退回一列 */
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 20px; }
.panel-card :deep(.el-divider) { margin: 10px 0; }
.mono-input :deep(.el-input__inner) { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }

@media (max-width: 1100px) {
  .fields { grid-template-columns: minmax(0, 1fr); }
  .panel-del { margin-left: 0; }
}
</style>
