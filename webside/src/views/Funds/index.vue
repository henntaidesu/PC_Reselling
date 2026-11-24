<template>
  <div class="funds-page" v-loading="loading">
    <div class="page-head">
      <h2 class="page-title">{{ t('route.funds') }}</h2>
      <div class="head-actions">
        <el-button :icon="Minus" @click="openDraw()">{{ t('funds.addDraw') }}</el-button>
        <el-button type="primary" :icon="Plus" @click="openInjection()">{{ t('funds.addInjection') }}</el-button>
      </div>
    </div>

    <!-- 总账：日元与人民币是同一笔钱的两种说法，压在同一张卡里（人民币作副行），
         四张卡在桌面一行排满、手机两行两列，不再出现 4 + 2 的半截行 -->
    <div class="kpi-grid">
      <StatCard v-for="card in statCards" :key="card.key" :label="card.label" :value="card.value"
        :sub="card.sub" :icon="card.icon" :color="card.color" :value-class="card.valueClass" />
    </div>
    <el-alert v-if="summary.shortfall" type="warning" :closable="false" show-icon class="mb"
      :title="t('funds.shortfallWarn', { amount: jpy(summary.shortfall) })" />
    <el-alert v-if="summary.incomplete" type="warning" :closable="false" show-icon class="mb"
      :title="t('funds.incompleteWarn')" />

    <!-- 按出资人：池子里的钱是谁出的、被花掉多少、还剩多少。
         全部由注资与分摊反算，没有单独的「账户」——余额有第二个地方存着就一定会对不上。
         一人一张卡，桌面和手机同一种排法（人数就几个，表格的列头反而占地方）；
         点一张卡 = 下面的注资批次与使用明细都只看这个人，再点一下取消。 -->
    <div v-if="contributors.length" class="section">
      <div class="section-head">
        <span class="section-title">{{ t('funds.contributors') }}</span>
        <el-button v-if="contributorFilter !== null" link type="primary" @click="contributorFilter = null">
          {{ t('funds.clearFilter') }}
        </el-button>
      </div>
      <div class="person-grid">
        <div v-for="row in contributors" :key="row.id ?? '__none__'" class="person"
          :class="{ 'is-active': contributorFilter === ckey(row.id), 'is-dimmed': contributorFilter !== null && contributorFilter !== ckey(row.id) }"
          @click="toggleContributor(row)">
          <div class="person-head">
            <el-tag size="small" :type="row.name ? 'primary' : 'info'" effect="plain">
              {{ row.name || t('funds.noContributor') }}
            </el-tag>
            <el-tooltip v-if="row.incomplete" :content="t('funds.rateMissingTag')">
              <el-icon class="warn-icon"><WarningFilled /></el-icon>
            </el-tooltip>
            <span class="person-share pcr-mono" :title="t('funds.share')">{{ percent(row.share) }}</span>
          </div>
          <div class="person-balance">
            <span class="pcr-dim">{{ t('funds.remaining') }}</span>
            <b class="pcr-mono" :class="{ 'is-owed': row.remaining < 0 }">{{ jpy(row.remaining) }}</b>
          </div>
          <!-- 用量条：已用 / 投入。欠款时整条变红——钱已经花超了 -->
          <div class="usage">
            <div class="usage-bar" :class="{ 'is-owed': row.remaining < 0 }"
              :style="{ width: usagePct(row) + '%' }" />
          </div>
          <div class="person-metrics">
            <div><span>{{ t('funds.injected') }}</span><b class="pcr-mono">{{ jpy(row.injected) }}</b>
              <i class="pcr-mono pcr-dim">{{ cny(row.injected_cny) }}</i></div>
            <div><span>{{ t('funds.used') }}</span><b class="pcr-mono">{{ jpy(row.used) }}</b>
              <i class="pcr-mono pcr-dim">{{ usagePct(row, true) }}</i></div>
            <div><span>{{ t('funds.avgRate') }}</span><b class="pcr-mono">{{ row.avg_rate ? formatRate(row.avg_rate) : '—' }}</b>
              <i v-if="row.shortfall" class="pcr-mono owed-text">{{ t('funds.shortfall') }} {{ jpy(row.shortfall) }}</i></div>
          </div>
        </div>
      </div>
    </div>

    <!-- 流水：注资批次与使用明细合成一张卡、按标签切换。并排两张半宽表时每张只有六七百像素，
         金额列挤成两行；整宽一张就摆得开。两边都跟着上面选中的出资人筛。 -->
    <el-card class="table-card" shadow="never">
      <div class="ledger-head">
        <el-tabs v-model="ledgerTab" class="ledger-tabs pcr-touch-tabs">
          <el-tab-pane name="injections">
            <template #label>{{ t('funds.injections') }} <span class="tab-count">{{ shownInjections.length }}</span></template>
          </el-tab-pane>
          <el-tab-pane name="draws">
            <template #label>{{ t('funds.draws') }} <span class="tab-count">{{ shownDraws.length }}</span></template>
          </el-tab-pane>
        </el-tabs>
        <el-tag v-if="contributorFilter !== null" closable size="small" type="primary" effect="dark"
          class="filter-chip" @close="contributorFilter = null">
          {{ t('funds.contributor') }}：{{ filterName }}
        </el-tag>
      </div>

      <!-- ── 注资批次 ── -->
      <template v-if="ledgerTab === 'injections'">
        <div v-if="isCompact" class="f-list f-list--grid">
          <div v-for="row in shownInjections" :key="row.id" class="f-item">
            <div class="f-head">
              <span class="pcr-mono pcr-dim">{{ row.inject_date }}</span>
              <el-tag v-if="row.contributor" size="small" type="primary" effect="plain">{{ row.contributor }}</el-tag>
              <el-tag v-if="row.earmark" size="small" type="warning" effect="dark">{{ t('funds.earmark') }} {{ row.earmark.mgmt_no }}</el-tag>
              <router-link v-if="row.sale_source" :to="saleLink(row.sale_source)" class="link">
                <el-tag size="small" type="success" effect="dark">{{ t('funds.typeSale') }} {{ row.sale_source.mgmt_no }}</el-tag>
              </router-link>
              <el-tag v-else-if="row.inject_type === 'cash'" size="small" type="success" effect="plain">{{ t('funds.typeCash') }}</el-tag>
              <el-tag v-else-if="row.fx_manual" size="small" type="warning" effect="plain">{{ t('funds.manualTag') }}</el-tag>
              <el-icon v-if="row.sale_source" class="f-edit pcr-dim"><Lock /></el-icon>
              <el-button v-else class="f-edit" :icon="EditPen" circle @click="openInjection(row)" />
            </div>
            <div class="f-metrics">
              <div><span>{{ t('funds.amount') }}</span><b class="pcr-mono">{{ jpy(row.amount) }}</b></div>
              <div><span>{{ t('funds.cnyCost') }}</span><b class="pcr-mono">{{ cny(row.cny_cost) }}</b>
                <i class="pcr-mono pcr-dim">@{{ row.fx_rate ? formatRate(row.fx_rate) : '—' }}</i></div>
              <div><span>{{ t('funds.remaining') }}</span><b class="pcr-mono">{{ jpy(row.remaining_amount) }}</b>
                <i class="pcr-dim">{{ t('funds.used') }} {{ jpy(row.used_amount) }}</i></div>
            </div>
            <div v-if="row.note" class="f-note pcr-dim">{{ row.note }}</div>
          </div>
        </div>
        <el-table v-else :data="shownInjections" class="pcr-table" size="small" empty-text=" ">
          <el-table-column :label="t('funds.injectDate')" width="110">
            <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.inject_date }}</span></template>
          </el-table-column>
          <el-table-column :label="t('funds.contributor')" min-width="180">
            <template #default="{ row }">
              <el-tag v-if="row.contributor" size="small" type="primary" effect="plain">{{ row.contributor }}</el-tag>
              <span v-else class="pcr-dim">—</span>
              <!-- 专款：只给这一件货扣（老货补录的那种），别的货吃不到它 -->
              <el-tag v-if="row.earmark" size="small" type="warning" effect="dark" class="earmark-tag">
                {{ t('funds.earmark') }} {{ row.earmark.mgmt_no }}
              </el-tag>
              <!-- 出售回流：这笔日元是哪件货卖出去收回来的，点进那件货 -->
              <router-link v-if="row.sale_source" :to="saleLink(row.sale_source)" class="link">
                <el-tag size="small" type="success" effect="dark" class="earmark-tag">
                  {{ t('funds.typeSale') }} {{ row.sale_source.mgmt_no }}
                </el-tag>
              </router-link>
              <el-tag v-else-if="row.inject_type === 'cash'" size="small" type="success" effect="plain" class="earmark-tag">{{ t('funds.typeCash') }}</el-tag>
              <el-tag v-else-if="row.fx_manual" size="small" type="warning" effect="plain" class="earmark-tag">{{ t('funds.manualTag') }}</el-tag>
              <div v-if="row.note" class="pcr-dim sub note-line">{{ row.note }}</div>
            </template>
          </el-table-column>
          <el-table-column :label="t('funds.amount')" align="right" min-width="120">
            <template #default="{ row }"><span class="pcr-mono">{{ jpy(row.amount) }}</span></template>
          </el-table-column>
          <!-- 现金注资也有汇率（注资日牌价），类型标签已经放在出资人那一列 -->
          <el-table-column :label="t('funds.rate')" align="right" width="100">
            <template #default="{ row }"><span class="pcr-mono">{{ row.fx_rate ? formatRate(row.fx_rate) : '—' }}</span></template>
          </el-table-column>
          <el-table-column :label="t('funds.cnyCost')" align="right" min-width="120">
            <template #default="{ row }"><span class="pcr-mono">{{ cny(row.cny_cost) }}</span></template>
          </el-table-column>
          <el-table-column :label="t('funds.used')" align="right" min-width="120">
            <template #default="{ row }"><span class="pcr-mono">{{ jpy(row.used_amount) }}</span></template>
          </el-table-column>
          <el-table-column :label="t('funds.remaining')" align="right" min-width="150">
            <template #default="{ row }">
              <div class="remain-cell">
                <span class="pcr-mono" :class="{ 'pcr-dim': !row.remaining_amount }">{{ jpy(row.remaining_amount) }}</span>
                <div class="usage usage--mini">
                  <div class="usage-bar" :style="{ width: batchUsedPct(row) + '%' }" />
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('common.actions')" width="62" align="center">
            <template #default="{ row }">
              <!-- 出售回流跟着货上的售价自动同步，在这里改了下次存货就被改回去 -->
              <el-tooltip v-if="row.sale_source" :content="t('funds.saleLocked')">
                <el-icon class="pcr-dim"><Lock /></el-icon>
              </el-tooltip>
              <el-button v-else link :icon="EditPen" @click="openInjection(row)" />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!shownInjections.length" :description="t('funds.noInjections')" :image-size="60" />
      </template>

      <!-- ── 使用明细 ── -->
      <template v-else>
        <!-- 点卡片展开分摊算式（与表格的展开行同一份内容）；编辑按钮和详情链接 stop 掉，
             不触发展开 -->
        <div v-if="isCompact" class="f-list f-list--grid">
          <div v-for="row in shownDraws" :key="row.id" class="f-item is-link" @click="toggleDraw(row.id)">
            <div class="f-head">
              <span class="pcr-mono pcr-dim">{{ row.draw_date }}</span>
              <el-tag v-if="row.owner_kind" size="small" effect="plain"
                :type="row.owner_kind === 'device' ? 'warning' : 'primary'">{{ t('inv.' + row.owner_kind) }}</el-tag>
              <span class="pcr-dim sub">{{ t('funds.cat.' + row.category) }}</span>
              <el-button v-if="!row.owner_kind" class="f-edit" :icon="EditPen" circle @click.stop="openDraw(row)" />
              <el-icon v-else class="f-edit pcr-dim"><Lock /></el-icon>
            </div>
            <div class="f-title">
              <router-link v-if="row.card_id" :to="`/cards/${row.card_id}`" class="link" @click.stop>{{ row.owner_name || row.mgmt_no }}</router-link>
              <router-link v-else-if="row.device_id" :to="`/devices/${row.device_id}`" class="link" @click.stop>{{ row.owner_name || row.mgmt_no }}</router-link>
              <span v-else>{{ row.note || t('funds.cat.other') }}</span>
              <el-tag v-if="row.contributor" size="small" type="primary" effect="plain">{{ row.contributor }}</el-tag>
              <el-tag v-if="row.shortfall" size="small" type="danger" effect="plain">{{ t('funds.shortfall') }}</el-tag>
            </div>
            <div class="f-metrics">
              <div><span>{{ t('funds.amount') }}</span><b class="pcr-mono">{{ jpy(row.amount) }}</b></div>
              <div><span>{{ t('funds.cnyCost') }}</span><b class="pcr-mono">{{ cny(row.cny_amount) }}</b>
                <i v-if="row.effective_rate" class="pcr-mono pcr-dim">@{{ formatRate(row.effective_rate) }}</i></div>
            </div>
            <div v-if="openDraws.has(row.id)" class="alloc f-alloc">
              <div v-for="(a, i) in row.allocations" :key="i" class="alloc-line">
                <span class="pcr-mono pcr-dim">{{ a.inject_date }}</span>
                <el-tag v-if="a.contributor" size="small" type="primary" effect="plain">{{ a.contributor }}</el-tag>
                <span class="pcr-mono">{{ jpy(a.amount) }}</span>
                <span class="pcr-dim">× {{ formatRate(a.fx_rate) }}/{{ RATE_UNIT }} =</span>
                <span class="pcr-mono">{{ cny(a.cny_amount) }}</span>
              </div>
              <div v-if="row.shortfall" class="alloc-line short">
                <span class="pcr-dim">{{ t('funds.shortfall') }}</span>
                <span class="pcr-mono">{{ jpy(row.shortfall) }}</span>
                <span class="pcr-dim">{{ t('funds.shortfallHint') }}</span>
              </div>
              <div v-if="!row.allocations.length && !row.shortfall" class="pcr-dim">{{ t('common.noData') }}</div>
            </div>
          </div>
        </div>
        <el-table v-else :data="shownDraws" class="pcr-table" size="small" row-key="id" empty-text=" ">
          <!-- 展开行就是这个功能的核心：一笔钱吃了哪几批注资、各按什么汇率折的 -->
          <el-table-column type="expand">
            <template #default="{ row }">
              <div class="alloc">
                <div v-for="(a, i) in row.allocations" :key="i" class="alloc-line">
                  <span class="pcr-mono pcr-dim">{{ a.inject_date }}</span>
                  <el-tag v-if="a.contributor" size="small" type="primary" effect="plain">{{ a.contributor }}</el-tag>
                  <span class="pcr-mono">{{ jpy(a.amount) }}</span>
                  <span class="pcr-dim">× {{ formatRate(a.fx_rate) }}/{{ RATE_UNIT }} =</span>
                  <span class="pcr-mono">{{ cny(a.cny_amount) }}</span>
                </div>
                <div v-if="row.shortfall" class="alloc-line short">
                  <span class="pcr-dim">{{ t('funds.shortfall') }}</span>
                  <span class="pcr-mono">{{ jpy(row.shortfall) }}</span>
                  <span class="pcr-dim">{{ t('funds.shortfallHint') }}</span>
                </div>
                <div v-if="!row.allocations.length && !row.shortfall" class="pcr-dim">{{ t('common.noData') }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column :label="t('funds.drawDate')" width="110">
            <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.draw_date }}</span></template>
          </el-table-column>
          <el-table-column :label="t('funds.purpose')" min-width="220">
            <template #default="{ row }">
              <!-- 扣款要么挂在一张卡上、要么挂在一台整机上（两者都有详情页，可点进去），
                   要么是手工记的池内支出 -->
              <router-link v-if="row.card_id" :to="`/cards/${row.card_id}`" class="link" @click.stop>
                {{ row.owner_name || row.mgmt_no }}
              </router-link>
              <router-link v-else-if="row.device_id" :to="`/devices/${row.device_id}`" class="link" @click.stop>
                {{ row.owner_name || row.mgmt_no }}
              </router-link>
              <span v-else>{{ row.note || t('funds.cat.other') }}</span>
              <div class="pcr-dim sub">
                <el-tag v-if="row.owner_kind" size="small" effect="plain"
                  :type="row.owner_kind === 'device' ? 'warning' : 'primary'" class="owner-tag">
                  {{ t('inv.' + row.owner_kind) }}
                </el-tag>
                {{ t('funds.cat.' + row.category) }}
              </div>
            </template>
          </el-table-column>
          <!-- 扣的是谁的池子：货的扣款就是归属人，手工支出是填的那个人 -->
          <el-table-column :label="t('funds.contributor')" min-width="110">
            <template #default="{ row }">
              <el-tag v-if="row.contributor" size="small" type="primary" effect="plain">{{ row.contributor }}</el-tag>
              <span v-else class="pcr-dim">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('funds.amount')" align="right" min-width="120">
            <template #default="{ row }">
              <div class="pcr-mono">{{ jpy(row.amount) }}</div>
              <div v-if="row.shortfall" class="sub pcr-mono owed-text">{{ t('funds.shortfall') }} {{ jpy(row.shortfall) }}</div>
            </template>
          </el-table-column>
          <el-table-column :label="t('funds.rate')" align="right" width="100">
            <template #default="{ row }"><span class="pcr-mono">{{ row.effective_rate ? formatRate(row.effective_rate) : '—' }}</span></template>
          </el-table-column>
          <el-table-column :label="t('funds.cnyCost')" align="right" min-width="120">
            <template #default="{ row }"><span class="pcr-mono">{{ cny(row.cny_amount) }}</span></template>
          </el-table-column>
          <el-table-column :label="t('common.actions')" width="62" align="center">
            <template #default="{ row }">
              <template v-if="!row.owner_kind">
                <el-button link :icon="EditPen" @click="openDraw(row)" />
              </template>
              <el-tooltip v-else :content="t('funds.ownerDrawLocked')">
                <el-icon class="pcr-dim"><Lock /></el-icon>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!shownDraws.length" :description="t('funds.noDraws')" :image-size="60" />
      </template>
    </el-card>

    <!-- 注资弹窗 -->
    <el-dialog v-model="injectionVisible" :title="injectionForm.id ? t('funds.editInjection') : t('funds.addInjection')" width="480px">
      <el-form :model="injectionForm" label-position="top">
        <el-form-item :label="t('funds.injectType')">
          <el-radio-group v-model="injectionForm.inject_type">
            <el-radio-button value="forex">{{ t('funds.typeForex') }}</el-radio-button>
            <el-radio-button value="cash">{{ t('funds.typeCash') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <!-- 日期与出资人并排：两者都短，各占一整行太空；窄屏（xs）退回上下排 -->
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12">
            <el-form-item :label="t('funds.injectDate')">
              <el-date-picker v-model="injectionForm.inject_date" type="date" value-format="YYYY-MM-DD" class="full"
                :editable="!isTouch" @change="previewRate" />
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item :label="t('funds.contributor')" required>
              <OwnerSelect v-model="injectionForm.contributor_id" class="full"
                :placeholder="t('funds.contributorPlaceholder')" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('funds.amount') + '（' + t('currency.JPY_short') + '）'">
          <el-input-number v-model="injectionForm.amount" :min="1" :step="10000" :precision="0" :controls="false" inputmode="numeric" class="full" />
        </el-form-item>
        <!-- 外汇注资：填日元与实付人民币，汇率由系统算；现金注资：没有换汇价可填，按注资日牌价记 -->
        <template v-if="injectionForm.inject_type === 'forex'">
          <el-form-item :label="t('funds.cnyPaid') + '（' + t('currency.CNY_short') + '）'">
            <el-input-number v-model="injectionForm.cny_cost" :min="0.01" :step="100" :precision="2"
              :controls="false" inputmode="decimal" class="full" />
          </el-form-item>
          <div v-if="manualRate" class="fx-hint">
            {{ t('funds.derivedRate') }}: {{ RATE_UNIT }} {{ t('currency.JPY_short') }} =
            {{ formatRate(manualRate) }} {{ t('currency.CNY_short') }}
            <span class="pcr-dim">（{{ t('funds.rateInverse', { rate: inverseRate(manualRate) }) }}）</span>
          </div>
        </template>
        <template v-else>
          <div v-if="ratePreview" class="fx-hint">
            {{ t('card.fxPreview') }}: {{ RATE_UNIT }} {{ t('currency.JPY_short') }} = {{ formatRate(ratePreview.rate) }} {{ t('currency.CNY_short') }}
            <span class="pcr-dim">（{{ ratePreview.rate_date }}{{ ratePreview.stale ? ' *' : '' }}）</span>
          </div>
          <div v-if="injectionCostPreview" class="fx-hint">
            {{ t('funds.cnyCost') }}: {{ cny(injectionCostPreview) }}
          </div>
        </template>
        <el-form-item :label="t('card.note')">
          <el-input v-model="injectionForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="injectionVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" :disabled="!injectionForm.contributor_id" @click="saveInjection">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 手工支出弹窗 -->
    <el-dialog v-model="drawVisible" :title="drawForm.id ? t('funds.editDraw') : t('funds.addDraw')" width="440px">
      <el-form :model="drawForm" label-position="top">
        <el-form-item :label="t('funds.drawDate')">
          <el-date-picker v-model="drawForm.draw_date" type="date" value-format="YYYY-MM-DD" class="full" :editable="!isTouch" />
        </el-form-item>
        <el-form-item :label="t('funds.amount') + '（' + t('currency.JPY_short') + '）'">
          <el-input-number v-model="drawForm.amount" :min="1" :step="1000" :precision="0" :controls="false" inputmode="numeric" class="full" />
        </el-form-item>
        <el-form-item :label="t('funds.contributor')">
          <OwnerSelect v-model="drawForm.contributor_id" class="full"
            :placeholder="t('funds.drawContribPlaceholder')" />
        </el-form-item>
        <el-form-item :label="t('card.note')">
          <el-input v-model="drawForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="drawVisible = false">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="saveDraw">{{ t('common.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { EditPen, Lock, Minus, Plus, WarningFilled } from '@element-plus/icons-vue'
import { fundsApi, fxApi } from '@/api'
import { ElMessage } from '@/utils/notify'
import { RATE_UNIT, cny, formatMoney, formatRate, inverseRate } from '@/utils/format'
import { useMetaStore } from '@/stores/meta'
import OwnerSelect from '@/components/OwnerSelect.vue'
import StatCard from '@/components/StatCard.vue'
import { useIsCompact, useIsTouch } from '@/composables/useIsMobile'

const { t } = useI18n()
const { isCompact } = useIsCompact()
const { isTouch } = useIsTouch()

const loading = ref(false)
const saving = ref(false)
const summary = ref({})
const injections = ref([])
const draws = ref([])
// 按人汇总（派生自注资与分摊）。下拉里的候选是用户名单（meta.people，见 OwnerSelect）：
// 一个刚建好还没注过资的人不在汇总里，却得能选到。
const meta = useMetaStore()
const contributors = ref([])
// 点「按出资人」里的一张卡，下面的注资批次与使用明细只看那个人的。null = 不筛。
// 注意 null 和 '' 不是一回事：'' 是「未指定出资人」那一档，它也能被筛。
// 按用户 id 分组而不是按名字：名字只是显示用的，改了名也还是同一个人。
const contributorFilter = ref(null)
const ckey = (id) => id ?? ''

const jpy = (v) => formatMoney(v, 'JPY')
const percent = (v) => (v == null ? '—' : (v * 100).toFixed(1) + '%')

const shownInjections = computed(() => {
  if (contributorFilter.value === null) return injections.value
  return injections.value.filter((r) => ckey(r.contributor_id) === contributorFilter.value)
})

// 扣款按「扣的是谁的池子」筛：货的扣款 contributor_id 就是归属人。专款等情况下分摊段
// 也可能落在别人的批次上，所以分摊里出现过这个人的也算——宁可多列一笔，不能漏掉他的钱去了哪。
const shownDraws = computed(() => {
  const key = contributorFilter.value
  if (key === null) return draws.value
  return draws.value.filter((d) => ckey(d.contributor_id) === key
    || (d.allocations || []).some((a) => ckey(a.contributor_id) === key))
})

const filterName = computed(() => {
  const row = contributors.value.find((c) => ckey(c.id) === contributorFilter.value)
  return row?.name || t('funds.noContributor')
})

// 再点同一个人取消筛选
function toggleContributor(row) {
  const key = ckey(row.id)
  contributorFilter.value = contributorFilter.value === key ? null : key
}

// 已用 / 投入。花超了（余额为负）封顶 100%，红色由样式表达
function usagePct(row, asText = false) {
  const pct = row.injected ? Math.min(100, Math.max(0, row.used / row.injected * 100)) : (row.remaining < 0 ? 100 : 0)
  return asText ? pct.toFixed(0) + '%' : pct
}
function batchUsedPct(row) {
  return row.amount ? Math.min(100, Math.max(0, row.used_amount / row.amount * 100)) : 0
}

const ledgerTab = ref('injections')

// 卡片列表里展开了分摊算式的扣款。可以同时展开好几笔（对账时常要并排比较），
// 所以是个集合而不是单个 id。
const openDraws = ref(new Set())
function toggleDraw(id) {
  const next = new Set(openDraws.value)
  next.has(id) ? next.delete(id) : next.add(id)
  openDraws.value = next
}

// 出售回流来自哪件货。整机带上部件类型，打开详情就停在卖掉的那一件上
function saleLink(src) {
  if (src.kind === 'card') return `/cards/${src.id}`
  return { path: `/devices/${src.id}`, query: src.part_type ? { tab: src.part_type } : {} }
}

const statCards = computed(() => {
  const s = summary.value
  return [
    { key: 'in', label: t('funds.totalInjected'), value: jpy(s.total_injected), sub: cny(s.total_injected_cny), icon: 'Wallet', color: '#5b8cff' },
    { key: 'out', label: t('funds.totalDrawn'), value: jpy(s.total_drawn), icon: 'Sell', color: '#e6a23c' },
    // 余额允许为负（欠款，等补注资），负的时候标红
    { key: 'balance', label: t('funds.balance'), value: jpy(s.balance), sub: cny(s.balance_cny), icon: 'Coin',
      color: s.balance < 0 ? '#F56C6C' : '#2ec4a6', valueClass: s.balance < 0 ? 'pcr-loss' : '' },
    { key: 'avg', label: t('funds.avgRate'), value: s.avg_rate ? formatRate(s.avg_rate) : '—', sub: s.avg_rate ? `${RATE_UNIT} ${t('currency.JPY_short')} → ${t('currency.CNY_short')}` : '', icon: 'TrendCharts', color: '#c471f5' }
  ]
})

// ── 数据 ────────────────────────────────────────────────────────────────
function apply(data, warnings) {
  summary.value = data.summary || {}
  injections.value = data.injections || []
  draws.value = data.draws || []
  contributors.value = data.contributors || []
  // 选中的人在新数据里没了（比如他唯一一笔注资刚被删掉），筛选跟着撤掉，别留一张空表
  if (contributorFilter.value !== null && !contributors.value.some((c) => ckey(c.id) === contributorFilter.value)) {
    contributorFilter.value = null
  }
  ;(warnings || data.warnings || []).forEach((w) => ElMessage.warning(w))
}

async function reload() {
  loading.value = true
  try {
    apply(await fundsApi.overview())
  } finally {
    loading.value = false
  }
}

// ── 注资 ────────────────────────────────────────────────────────────────
const injectionVisible = ref(false)
const ratePreview = ref(null)
const injectionForm = reactive({ id: null, inject_type: 'forex', inject_date: null, amount: null, cny_cost: null, contributor_id: null, note: null })

// 出资人必选（后端同样校验）：没写出资人的批次在按人分摊里找不到主人，只能被全池 FIFO 吃掉。

// 现金注资按牌价记，先让人看到「这笔钱折多少人民币」——注资的意义就在这个数上。
// 外汇注资的这个数就是上面填的实付，不用再显示一遍。
const injectionCostPreview = computed(() => {
  if (injectionForm.inject_type !== 'cash') return null
  const rate = ratePreview.value?.rate
  if (!rate || !injectionForm.amount) return null
  return injectionForm.amount * rate / RATE_UNIT
})

// 汇率不用人填：实付人民币 ÷ 换到的日元 × 100 就是这批钱的真实汇率，存进去的也是它。
// 后端 funds.manual_rate 会照同一个算式再算一遍，这里只管让人在保存前看见。
const manualRate = computed(() => {
  if (injectionForm.inject_type === 'cash' || !injectionForm.cny_cost || !injectionForm.amount) return null
  return injectionForm.cny_cost / injectionForm.amount * RATE_UNIT
})

function openInjection(row = null) {
  Object.assign(injectionForm, {
    id: row?.id ?? null,
    inject_type: row?.inject_type ?? 'forex',
    inject_date: row?.inject_date ?? new Date().toISOString().slice(0, 10),
    amount: row?.amount ?? null,
    // 外汇注资必须填实付人民币。编辑旧数据时带上它现在折出来的人民币：手填过的就是原值，
    // 早年按牌价自动取的那种也有个起点可改，不至于一打开就是空的、保存不了。
    cny_cost: row && row.inject_type !== 'cash' ? row.cny_cost : null,
    contributor_id: row?.contributor_id ?? null,
    note: row?.note ?? null
  })
  ratePreview.value = null
  injectionVisible.value = true
  previewRate()
}

async function previewRate() {
  if (!injectionForm.inject_date) { ratePreview.value = null; return }
  try {
    ratePreview.value = await fxApi.rate({ date: injectionForm.inject_date })
  } catch {
    ratePreview.value = null
  }
}

async function saveInjection() {
  if (!injectionForm.inject_date || !injectionForm.amount) {
    ElMessage.warning(t('funds.requireDateAmount'))
    return
  }
  const isCash = injectionForm.inject_type === 'cash'
  if (!isCash && !injectionForm.cny_cost) {
    ElMessage.warning(t('funds.requireCnyPaid'))
    return
  }
  const payload = {
    inject_date: injectionForm.inject_date,
    amount: injectionForm.amount,
    inject_type: injectionForm.inject_type,
    cny_cost: isCash ? null : injectionForm.cny_cost,
    contributor_id: injectionForm.contributor_id,
    note: injectionForm.note
  }
  saving.value = true
  try {
    const res = injectionForm.id
      ? await fundsApi.updateInjection(injectionForm.id, payload)
      : await fundsApi.createInjection(payload)
    apply(res)
    injectionVisible.value = false
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}

// ── 手工支出 ────────────────────────────────────────────────────────────
const drawVisible = ref(false)
const drawForm = reactive({ id: null, draw_date: null, amount: null, contributor_id: null, note: null })

function openDraw(row = null) {
  Object.assign(drawForm, {
    id: row?.id ?? null,
    draw_date: row?.draw_date ?? new Date().toISOString().slice(0, 10),
    amount: row?.amount ?? null,
    contributor_id: row?.contributor_id ?? null,
    note: row?.note ?? null
  })
  drawVisible.value = true
}

async function saveDraw() {
  if (!drawForm.draw_date || !drawForm.amount) {
    ElMessage.warning(t('funds.requireDateAmount'))
    return
  }
  const payload = {
    draw_date: drawForm.draw_date, amount: drawForm.amount,
    contributor_id: drawForm.contributor_id || null, note: drawForm.note,
  }
  saving.value = true
  try {
    const res = drawForm.id
      ? await fundsApi.updateDraw(drawForm.id, payload)
      : await fundsApi.createDraw(payload)
    apply(res)
    drawVisible.value = false
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    saving.value = false
  }
}

onMounted(() => {
  meta.ensure()
  reload()
})
</script>

<style scoped>
.page-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.page-title { font-size: 20px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.mb { margin-bottom: 12px; }
.table-card { margin-bottom: 16px; }
/* 余额为负 = 欠着池子的钱，等补注资 */
.is-owed { color: var(--pcr-loss); }
.owed-text { color: var(--pcr-loss); }
.earmark-tag { margin-left: 4px; }
.sub { font-size: 11px; }
.note-line { margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.owner-tag { margin-right: 4px; transform: scale(0.85); transform-origin: left center; }
.link { color: #8fb8ff; text-decoration: none; }
.link:hover { text-decoration: underline; }
.full { width: 100% !important; }
.fx-hint {
  margin: 0 0 12px;
  padding: 6px 10px;
  font-size: 12px;
  color: #b9c4d6;
  background: rgba(91, 140, 255, 0.08);
  border-radius: 6px;
}
.alloc { padding: 4px 12px 8px 46px; }
.alloc-line { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 3px 0; color: #c7d0de; }
.alloc-line.short { color: #e6a23c; }

/* ── 总账 ── 四张等宽，平板 / 手机两列 */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

/* ── 按出资人 ── */
.section { margin-bottom: 16px; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; min-height: 24px; }
.section-title { font-size: 14px; font-weight: 600; color: var(--pcr-text); }
.person-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}
.person {
  padding: 12px 14px;
  border: 1px solid var(--pcr-border);
  border-radius: 8px;
  background: var(--pcr-card);
  cursor: pointer;
  min-width: 0;
  transition: border-color .15s, opacity .15s, background .15s;
}
.person:hover { border-color: #3d5a99; }
.person.is-active { border-color: var(--pcr-accent); background: rgba(91, 140, 255, 0.08); }
/* 选中一个人时其余的压暗：一眼看出下面的流水是按谁筛的 */
.person.is-dimmed { opacity: 0.55; }
.person-head { display: flex; align-items: center; gap: 6px; }
.warn-icon { color: #e6a23c; }
.person-share { margin-left: auto; font-size: 13px; color: var(--pcr-text-dim); }
.person-balance { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-top: 10px; }
.person-balance span { font-size: 12px; }
.person-balance b { font-size: 20px; font-weight: 700; color: var(--pcr-text); overflow-wrap: anywhere; }
.person-balance b.is-owed { color: var(--pcr-loss); }
.usage { height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.06); overflow: hidden; margin-top: 8px; }
.usage-bar { height: 100%; background: var(--pcr-accent); border-radius: 2px; }
.usage-bar.is-owed { background: var(--pcr-loss); }
.usage--mini { width: 64px; margin-top: 0; flex-shrink: 0; }
.person-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.person-metrics > div { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.person-metrics span { font-size: 11px; color: #8a94a6; }
.person-metrics b { font-size: 13px; font-weight: 600; color: var(--pcr-text); overflow-wrap: anywhere; }
.person-metrics i { font-style: normal; font-size: 11px; overflow-wrap: anywhere; }

/* ── 流水卡：标签条当卡头用 ── */
.ledger-head { display: flex; align-items: center; gap: 12px; margin: -8px 0 8px; }
.ledger-tabs { flex: 1; min-width: 0; }
.ledger-tabs :deep(.el-tabs__header) { margin: 0; }
.ledger-tabs :deep(.el-tabs__nav-wrap::after) { height: 1px; background: var(--pcr-border); }
.tab-count {
  display: inline-block;
  min-width: 18px;
  padding: 0 5px;
  margin-left: 4px;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.08);
  color: var(--pcr-text-dim);
}
.filter-chip { flex-shrink: 0; }
.remain-cell { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }

@media (max-width: 1200px) {
  .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 768px) {
  .kpi-grid { gap: 8px; }
  /* 两个操作按钮各占半行，热区够大 */
  .head-actions { width: 100%; }
  .head-actions .el-button { flex: 1 1 40%; margin-left: 0; }
  .person-grid { grid-template-columns: minmax(0, 1fr); gap: 8px; }
  /* 卡片列表自带边框，外面那张卡的内边距收窄，别两层留白叠在一起 */
  .table-card :deep(.el-card__body) { padding: 8px; }
  .ledger-head { margin: 0 0 8px; flex-wrap: wrap; }
  /* 窄屏上金额常到七位，三列会把「￥1,234,567」折成两行；两列正好 */
  .f-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* ── 卡片列表（紧凑宽度：手机 + 平板）──────────────────────────────
   两张流水表在 ≤1200px 换成这里的卡片：同一份数据、同一个筛选 / 编辑入口，不持有自己的状态
   （只多了「哪几笔扣款展开着」这一个纯展示的集合）。 */
.f-list { display: flex; flex-direction: column; gap: 8px; }
.f-item {
  padding: 10px 12px;
  border: 1px solid var(--pcr-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.015);
  min-width: 0;
}
.f-item.is-link { cursor: pointer; }
.f-item.is-link:active { background: rgba(91, 140, 255, 0.08); }
.f-head { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; min-height: 32px; }
/* 编辑按钮 / 锁一律推到行尾，和左边的日期、标签分开 */
.f-edit { margin-left: auto; }
.f-title { margin-top: 4px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 14px; color: #e6edf7; }
.f-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 10px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--pcr-border);
}
.f-metrics > div { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.f-metrics span { font-size: 11px; color: #8a94a6; }
.f-metrics b { font-size: 14px; font-weight: 600; color: #e6edf7; overflow-wrap: anywhere; }
.f-metrics i { font-style: normal; font-size: 11px; overflow-wrap: anywhere; }
.f-note { margin-top: 6px; font-size: 12px; overflow-wrap: anywhere; }
/* 分摊算式在卡片里不需要桌面展开行那 46px 的左缩进（那是对齐展开箭头用的） */
.f-alloc { margin-top: 8px; padding: 6px 0 0; border-top: 1px dashed var(--pcr-border); }
.f-alloc .alloc-line { flex-wrap: wrap; gap: 4px 8px; }

/* 平板：流水卡片两列排 */
@media (min-width: 769px) and (max-width: 1200px) {
  .f-list--grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
    gap: 10px;
  }
}
/* 编辑按钮默认 32px 圆，触屏上再大一点，和卡片上「点了展开」的区域分得开 */
@media (hover: none) {
  .f-edit.el-button { width: 36px; height: 36px; }
}
</style>
