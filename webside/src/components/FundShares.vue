<template>
  <!-- 「这件货的钱由谁出、各占多少」。显卡和整机是同一件事，所以同一个组件，
       别在两个详情页里各画一遍——比例的校验规则写两份，迟早只改其中一份。 -->
  <div class="fund-shares">
    <el-select v-model="names" multiple filterable allow-create default-first-option
      collapse-tags collapse-tags-tooltip class="picker"
      :placeholder="t('fundShare.placeholder')" @change="onNamesChange">
      <el-option v-for="n in options" :key="n" :label="n" :value="n" />
    </el-select>

    <!-- 一个人时不出比例输入：只有一个出资人，比例只能是 100%，摆个输入框出来
         等于请人填一个唯一答案。两个人起才需要分。 -->
    <div v-if="names.length > 1" class="rows">
      <div v-for="n in names" :key="n" class="row">
        <span class="name" :title="n">{{ n }}</span>
        <el-input-number v-model="pct[n]" :min="0" :max="100" :precision="2" :step="5"
          :controls="false" size="small" class="pct" @change="publish" />
        <span class="unit">%</span>
      </div>
      <div class="sum" :class="{ bad: !sumOk }">
        <span>{{ t('fundShare.sum', { n: shownSum }) }}</span>
        <el-button link type="primary" size="small" @click="distributeEvenly">
          {{ t('fundShare.even') }}
        </el-button>
      </div>
      <!-- 加不满 100 就不往上抛（见 publish），所以这行必须显眼：
           不然「改了却没存上」看着像丢数据 -->
      <div v-if="!sumOk" class="warn">{{ t('fundShare.sumWarn') }}</div>
    </div>
    <div v-else-if="names.length === 1" class="single pcr-dim">{{ t('fundShare.single') }}</div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

// modelValue 形状与后端一致：[{ contributor, share_pct }]，share_pct 是百分数（60 = 六成）。
// 前后端同一个单位，页面上填的数就是库里存的数，中间没有第二次换算。
const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] }
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()

const names = ref([])
const pct = reactive({})

const sum = computed(() => names.value.reduce((acc, n) => acc + (Number(pct[n]) || 0), 0))
const shownSum = computed(() => Math.round(sum.value * 100) / 100)
// 浮点加法的零头（33.33 × 3）不该被判成不合法，留一分钱容差，与后端同一个口径
const sumOk = computed(() => Math.abs(sum.value - 100) <= 0.01)

// 父组件的值是唯一事实来源，这里只管回填，**不在这里 emit**。
// 抛回去的只有用户的操作（@change），所以不存在「父传子、子又传父」那种回环——
// 在自动保存的详情页里，那种回环表现为一进页面就白存一遍。
watch(() => props.modelValue, (val) => {
  names.value = (val || []).map((s) => s.contributor)
  for (const key of Object.keys(pct)) delete pct[key]
  for (const s of (val || [])) pct[s.contributor] = Number(s.share_pct)
}, { immediate: true, deep: true })

// 人选变了就重新平均分。刚勾上第二个人时「100 / 0」是个不合法的中间态，而在自动保存
// 的页面里，不合法的中间态要么是一次失败的请求、要么是一次悄悄不保存；平均分是这时
// 唯一说得通的默认值。代价是原来手调的 60/40 会被重置——加人本来就让旧比例失效了。
function onNamesChange() {
  for (const key of Object.keys(pct)) {
    if (!names.value.includes(key)) delete pct[key]
  }
  distributeEvenly()
}

function distributeEvenly() {
  const n = names.value.length
  if (n > 1) {
    const each = Math.floor(10000 / n) / 100
    names.value.forEach((name, i) => {
      // 最后一个吃掉余数：三个人各 33.33 只有 99.99，差的那一分必须有人承担，
      // 否则这组比例永远达不到 100，也就永远存不进去
      pct[name] = i === n - 1 ? Math.round((100 - each * (n - 1)) * 100) / 100 : each
    })
  }
  publish()
}

// 只在合法时抛给父组件。详情页是改一个字段就 PUT 一次的，抛一组加不满 100 的比例
// 上去，后端会 400，用户每敲一下就吃一个红色提示——而他只是还没填完。
function publish() {
  if (!names.value.length) { emit('update:modelValue', []); return }
  if (names.value.length === 1) {
    emit('update:modelValue', [{ contributor: names.value[0], share_pct: 100 }])
    return
  }
  if (!sumOk.value) return
  emit('update:modelValue', names.value.map((n) => ({
    contributor: n,
    share_pct: Number(pct[n]) || 0
  })))
}
</script>

<style scoped>
.fund-shares { width: 100%; }
.picker { width: 100%; }
.rows { margin-top: 6px; }
.row { display: flex; align-items: center; gap: 8px; padding: 2px 0; }
.name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
.pct { width: 92px; }
.unit { font-size: 12px; color: #9aa6b8; }
.sum { display: flex; align-items: center; justify-content: space-between; font-size: 12px; color: #9aa6b8; padding-top: 4px; }
.sum.bad { color: #e6a23c; }
.warn { font-size: 12px; color: #e6a23c; line-height: 1.5; }
.single { font-size: 12px; margin-top: 4px; }

@media (hover: none) {
  /* 触屏上这几行要用手指点：比例输入框的默认高度是按鼠标设计的，指头点不准，
     而点歪了会落到旁边那个人的格子里，改完还看不出改错了谁 */
  .row { padding: 4px 0; }
  .pct { width: 110px; }
}
</style>
