<template>
  <!-- 整机详情「部件」模块右侧的编辑区：一次只编辑左边列表里选中的那一件。
       只有字段（两列网格），这件的图片在详情右侧的图片侧栏。 -->
  <div class="part-editor">
    <div class="pe-head">
      <PartTypeTag :type="part.part_type" />
      <span class="pe-title" :class="{ 'pcr-dim': blank }">{{ blank ? t('device.blankSlot') : title }}</span>
      <span v-if="net !== null" class="pcr-dim pe-net">
        {{ t('device.netIncome') }} <b class="pcr-mono">{{ cny(net) }}</b>
      </span>
      <!-- 同类只剩这一件时不给删（deletable=false）：一台机器不可能没有 CPU，
           与其删掉再让人从「添加」里加回来，不如根本不摆这个按钮 -->
      <!-- 置换：只有显卡部件能和单卡互换实物。还没落盘（没 id）或已经卖出的不给 -->
      <el-button v-if="swappable" class="pe-swap" size="small" text type="primary" :icon="Switch"
        @click="emit('swap')">
        {{ t('swap.action') }}
      </el-button>
      <el-button v-if="deletable" class="pe-del" size="small" text type="danger" :icon="Delete"
        @click="emit('remove')">
        {{ t('device.removePart') }}
      </el-button>
    </div>

    <el-form label-position="top" size="small" class="pcr-form pd-form" @submit.prevent>
      <el-form-item :label="t('card.brand')">
        <!-- 品牌候选按部件类型给：CPU 只有 Intel / AMD（不允许现场新建），显卡直接用
             系统里的品牌字典，其余给一份常见清单但可以现场输入 -->
        <el-select v-model="part.brand" filterable :allow-create="!schema.brandStrict"
          default-first-option clearable>
          <el-option v-for="b in brandOptions" :key="b" :label="b" :value="b" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('card.model')">
        <el-select v-if="modelOptions.length" v-model="part.model" filterable allow-create
          default-first-option clearable>
          <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
        </el-select>
        <el-input v-else v-model="part.model" />
      </el-form-item>
      <!-- 「规格」这一栏各类型填的不是一回事（核心编号 / 容量 / 功率 / 芯片组），标题跟着类型走 -->
      <el-form-item :label="t(specLabelKey(part.part_type))">
        <el-input v-model="part.spec" />
      </el-form-item>
      <el-form-item :label="t('card.serialNo')">
        <el-input v-model="part.serial_no" autocapitalize="off" autocorrect="off" spellcheck="false" />
      </el-form-item>
      <el-form-item :label="t('card.saleDate')">
        <el-date-picker v-model="part.sale_date" type="date" value-format="YYYY-MM-DD" :editable="!isTouch" />
      </el-form-item>
      <el-form-item :label="t('card.status')">
        <StatusSelect v-model="part.status" />
      </el-form-item>
      <!-- 空着 = 跟随整机。只有这一件确实归了别人（比如置换进来的那块卡还算单的）才填 -->
      <el-form-item :label="t('owner.label')">
        <OwnerSelect v-model="part.owner"
          :placeholder="deviceOwner ? t('owner.followDeviceOf', { name: deviceOwner }) : t('owner.followDevice')" />
      </el-form-item>
      <el-form-item :label="t('card.saleAmount')">
        <MoneyInput v-model:amount="part.sale_amount" v-model:currency="part.sale_currency" />
      </el-form-item>
      <el-form-item :label="t('card.domesticShipping')">
        <MoneyInput v-model:amount="part.domestic_shipping_amount"
          v-model:currency="part.domestic_shipping_currency" />
      </el-form-item>
      <el-form-item :label="t('card.note')" class="pcr-span-2">
        <el-input v-model="part.note" type="textarea" :rows="2" resize="none" />
      </el-form-item>
    </el-form>
    <!-- 这一件的图片不在这里，在详情右侧的图片侧栏：选中部件时侧栏换成它的图 -->
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Delete, Switch } from '@element-plus/icons-vue'
import { cny } from '@/utils/format'
import { hasPartContent, partSchema, specLabelKey } from '@/constants/parts'
import { useMetaStore } from '@/stores/meta'
import { useIsTouch } from '@/composables/useIsMobile'
import PartTypeTag from './PartTypeTag.vue'
import MoneyInput from './MoneyInput.vue'
import StatusSelect from './StatusSelect.vue'
import OwnerSelect from './OwnerSelect.vue'

// 这里**直接改 part 上的字段**（v-model="part.brand"）。part 就是详情页 form.parts
// 里的那个对象，改它正是目的：页面的深层 watch 会看到，600ms 后自动落盘。若改成
// 逐字段 emit 回去，十来个字段 × 每个都要一条事件，除了噪音没有任何好处。
const props = defineProps({
  part: { type: Object, required: true },
  // 这个部件折人民币后的净收入，由页面从上次保存的返回值里按 id 取
  net: { type: Number, default: null },
  // 能不能删。同类只剩一件的必有槽位传 false
  deletable: { type: Boolean, default: true },
  // 整机的归属人：部件自己没填时就是它，用作下拉的占位提示
  deviceOwner: { type: String, default: null }
})
const emit = defineEmits(['remove', 'swap'])

const { t } = useI18n()
const meta = useMetaStore()
const { isTouch } = useIsTouch()

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
// 置换按库里的那一行来换，所以必须已经存过（有 id）；卖掉的在买家手里，换不了
const swappable = computed(() =>
  props.part.part_type === 'gpu' && Boolean(props.part.id) && !sold.value &&
  !['received', 'paid'].includes(props.part.status)
)
const title = computed(() =>
  [props.part.brand, props.part.model, props.part.spec].filter(Boolean).join(' ') || '—'
)
</script>

<style scoped>
.pe-head { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }
.pe-title { font-size: 15px; color: #e6edf7; font-weight: 500; }
.pe-net { font-size: 12px; }
.pe-swap { margin-left: auto; }
.pe-del { margin-left: auto; }
.pe-swap + .pe-del { margin-left: 0; }
/* 「删除部件」是 small 文字按钮，24px 高——触屏上撑到能按准 */
@media (hover: none) {
  .pe-del, .pe-swap { min-height: 34px; padding: 8px 10px; }
}
</style>
