<template>
  <div class="cards-page">
    <div class="page-head">
      <h2 class="page-title">{{ t('route.cards') }}</h2>
    </div>

    <!-- 统计模块：随下方筛选联动，覆盖整个筛选结果（不只当前页），显卡与整机合计。
         手机端不展示——8 张卡两列排下来要划掉大半屏才看得到表格。 -->
    <el-card v-if="!isMobile" class="stats-card" shadow="never">
      <div v-loading="statsLoading">
        <el-row :gutter="16" class="stat-row">
          <el-col v-for="card in statCards" :key="card.key" :xs="12" :sm="8" :md="8" :lg="6" :xl="3">
            <StatCard
              :label="card.label"
              :value="card.value"
              :sub="card.sub"
              :icon="card.icon"
              :color="card.color"
              :value-class="card.valueClass"
            />
          </el-col>
        </el-row>
        <div v-if="stats.incomplete" class="stats-warn">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ t('dashboard.incompleteWarn', { n: stats.incomplete }) }}</span>
        </div>
      </div>
    </el-card>

    <!-- 筛选行 -->
    <el-card class="filter-card" shadow="never">
      <div class="filters">
        <el-input
          v-model="filters.keyword"
          :placeholder="t('common.search')"
          clearable
          class="f-keyword"
          @keyup.enter="reload"
          @clear="reload"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <!-- 手机上六个筛选器竖着排完要占掉大半屏，进页面第一眼看到的是一列空下拉框而
             不是货。所以窄屏默认只留搜索框，其余收进这个开关；按钮上的角标写着当前有
             几项在生效——收起来之后唯一的风险就是「明明有货却一条都不显示」而看不出
             是筛掉的。 -->
        <el-button v-if="isMobile" class="f-toggle" :icon="Filter" @click="filtersOpen = !filtersOpen">
          {{ t('common.filter') }}<span v-if="activeFilterCount" class="f-count">{{ activeFilterCount }}</span>
        </el-button>
        <template v-if="!isMobile || filtersOpen">
          <!-- 所有下拉的选项都是联动的（后端 /inventory/facets）：按「其余筛选全部生效、
               只放开它自己」时还剩几件来列，后面的数字就是选它之后会筛出的条数。
               选了显卡，品牌 / 型号里就只剩显卡上出现过的；选了品牌，类型里也只剩有这个
               品牌的那几类。 -->
          <!-- 类型分两组：商品（显卡单品 / 整机）与部件。选部件时整机不再整台出现，而是
               把每台里该类型的部件逐个列成一行（后端 _solo_part），点开进所属整机。
               两组里都有「显卡」，靠分组标题区分：上面是单卖的卡，下面是整机拆出来的那块。 -->
          <el-select v-model="filters.kind" :placeholder="t('inv.allKinds')" clearable class="f-kind" @change="reload">
            <el-option-group v-if="kindGoods.length" :label="t('inv.groupGoods')">
              <el-option v-for="o in kindGoods" :key="o.value" :label="kindLabel(o.value)" :value="o.value">
                <FacetLabel :label="kindLabel(o.value)" :count="o.count" />
              </el-option>
            </el-option-group>
            <el-option-group v-if="kindParts.length" :label="t('inv.groupParts')">
              <el-option v-for="o in kindParts" :key="o.value" :label="kindLabel(o.value)" :value="o.value">
                <FacetLabel :label="kindLabel(o.value)" :count="o.count" />
              </el-option>
            </el-option-group>
          </el-select>
          <StatusSelect v-model="filters.status" multiple collapse-tags :placeholder="t('card.status')"
            :options="facetValues('status', filters.status)" :counts="facetCounts('status')"
            clearable class="f-status" @change="reload" />
          <el-select v-model="filters.brand" :placeholder="t('card.brand')" clearable filterable class="f-brand" @change="reload">
            <el-option v-for="o in facetOptions('brand', filters.brand)" :key="o.value" :label="o.value" :value="o.value">
              <FacetLabel :label="o.value" :count="o.count" />
            </el-option>
          </el-select>
          <!-- 型号：显卡单品与整机部件合在一起数。整机本身没有型号，所以类型没选「整机」时
               命中的是那个部件，单独列成一行（后端 _select） -->
          <el-select v-model="filters.model" :placeholder="t('card.model')" clearable filterable class="f-model" @change="reload">
            <el-option v-for="o in facetOptions('model', filters.model)" :key="o.value" :label="o.value" :value="o.value">
              <FacetLabel :label="o.value" :count="o.count" />
            </el-option>
          </el-select>
          <el-select v-model="filters.source_platform" :placeholder="t('card.platform')" clearable class="f-platform" @change="reload">
            <el-option v-for="o in facetOptions('source_platform', filters.source_platform)" :key="o.value"
              :label="platformLabel(o.value)" :value="o.value">
              <FacetLabel :label="platformLabel(o.value)" :count="o.count" />
            </el-option>
          </el-select>
          <!-- 归属人：货是谁的，也是钱从谁的池里扣。整机里有部件单独归别人时，按那个人筛
               也会出这台整机（见 inventory_api._device_item 的 owners）。「未指定」挑出
               没设归属人、也就没走资金池的那些。 -->
          <el-select v-model="filters.owner" multiple collapse-tags clearable filterable
            :placeholder="t('owner.label')" class="f-owner" @change="reload">
            <el-option v-for="o in facetOptions('owner', filters.owner)" :key="o.value"
              :label="ownerLabel(o.value)" :value="o.value">
              <FacetLabel :label="ownerLabel(o.value)" :count="o.count" />
            </el-option>
          </el-select>
          <!-- 区间选择器在手机上摆不下：Element 的 daterange 面板是并排两个月历，
               写死 646px 宽（单个月历是 322px），360px 的屏上会被裁掉大半，右边那个月
               连同「确定」一起看不见。窄屏拆成起 / 止两个单日期选择器——面板只剩一个月，
               正好放得下，顺带也支持只填一头（后端两端本来就是各自独立判断的）。 -->
          <el-date-picker
            v-if="!isMobile"
            v-model="dateRange"
            type="daterange"
            :editable="!isTouch"
            value-format="YYYY-MM-DD"
            :start-placeholder="t('card.purchaseDate')"
            :end-placeholder="t('card.purchaseDate')"
            class="f-date"
            @change="reload"
          />
          <template v-else>
            <el-date-picker
              :model-value="dateRange?.[0] || null"
              type="date"
              :editable="!isTouch"
              value-format="YYYY-MM-DD"
              :placeholder="t('inv.dateFrom')"
              class="f-date"
              @update:model-value="(v) => setRangeEnd(dateRange, 0, v)"
            />
            <el-date-picker
              :model-value="dateRange?.[1] || null"
              type="date"
              :editable="!isTouch"
              value-format="YYYY-MM-DD"
              :placeholder="t('inv.dateTo')"
              class="f-date"
              @update:model-value="(v) => setRangeEnd(dateRange, 1, v)"
            />
          </template>
          <!-- 「更多筛选」只在宽屏有：手机上整组筛选器已经收在「筛选」开关后面了，
               再套一层开关就得点两下才看得到。角标同「筛选」按钮——收起来的条件在生效
               时必须看得出来。 -->
          <el-button v-if="!isMobile" :icon="moreOpen ? ArrowUp : ArrowDown" @click="moreOpen = !moreOpen">
            {{ t('inv.moreFilters') }}<span v-if="moreFilterCount" class="f-count">{{ moreFilterCount }}</span>
          </el-button>
          <el-button :icon="Refresh" @click="resetFilters">{{ t('common.reset') }}</el-button>
        </template>
        <!-- 新增挨着重置放：这一行是「对这张表做点什么」的地方，按钮都聚在同一处，
             不用在标题栏和筛选行之间来回找 -->
        <el-button type="primary" :icon="Plus" class="f-add" @click="addVisible = true">{{ t('common.add') }}</el-button>
        <!-- 表格 / 卡片切换只在宽屏给：紧凑宽度以下本来就只有卡片这一种排法，
             摆个开关在那儿，切到「表格」也不会有任何变化。 -->
        <el-radio-group v-if="!isCompact" v-model="viewMode" class="f-view">
          <el-radio-button value="table">
            <el-tooltip :content="t('inv.viewTable')"><el-icon><List /></el-icon></el-tooltip>
          </el-radio-button>
          <el-radio-button value="cards">
            <el-tooltip :content="t('inv.viewCards')"><el-icon><Grid /></el-icon></el-tooltip>
          </el-radio-button>
        </el-radio-group>
      </div>
      <!-- 第二排：按算出来的值筛（出售日期、结清、盈亏、池内扣除、成本）。这些都不是
           数据库列，后端在规范化之后筛（inventory_api._match_derived），与列表上显示的
           数同一个口径。 -->
      <div v-if="isMobile ? filtersOpen : moreOpen" class="filters filters-more">
        <el-date-picker
          v-if="!isMobile"
          v-model="saleRange"
          type="daterange"
          :editable="!isTouch"
          value-format="YYYY-MM-DD"
          :start-placeholder="t('card.saleDate')"
          :end-placeholder="t('card.saleDate')"
          class="f-date"
          @change="reload"
        />
        <template v-else>
          <el-date-picker
            :model-value="saleRange?.[0] || null"
            type="date"
            :editable="!isTouch"
            value-format="YYYY-MM-DD"
            :placeholder="t('inv.saleFrom')"
            class="f-date"
            @update:model-value="(v) => setRangeEnd(saleRange, 0, v)"
          />
          <el-date-picker
            :model-value="saleRange?.[1] || null"
            type="date"
            :editable="!isTouch"
            value-format="YYYY-MM-DD"
            :placeholder="t('inv.saleTo')"
            class="f-date"
            @update:model-value="(v) => setRangeEnd(saleRange, 1, v)"
          />
        </template>
        <el-select v-for="sel in DERIVED_SELECTS" :key="sel.key" v-model="filters[sel.key]"
          :placeholder="t(sel.placeholder)" clearable class="f-small" @change="reload">
          <el-option v-for="o in facetOptions(sel.key, filters[sel.key])" :key="o.value"
            :label="t(sel.labels[o.value])" :value="o.value">
            <FacetLabel :label="t(sel.labels[o.value])" :count="o.count" />
          </el-option>
        </el-select>
        <!-- 成本区间按人民币总成本（含两笔运费），与「总成本」列同一个数。
             改完不立刻取数：敲「1500」会先后按 1、15、150 各筛一遍，等失焦或回车再说。 -->
        <div class="f-cost">
          <el-input-number v-model="filters.costMin" :min="0" :controls="false" :placeholder="t('inv.costMin')"
            inputmode="decimal" class="f-cost-input" @change="reload" />
          <span class="pcr-dim">~</span>
          <el-input-number v-model="filters.costMax" :min="0" :controls="false" :placeholder="t('inv.costMax')"
            inputmode="decimal" class="f-cost-input" @change="reload" />
        </div>
      </div>
    </el-card>

    <!-- 表格：显卡与整机同一张表，靠「类型」列区分。整机可展开看部件明细 -->
    <el-card class="table-card" shadow="never">
      <!-- 手机改用卡片列表。这张表十一列合计约 1400px，在 360px 的屏上要横着划近四屏，
           而「哪一张卡、卖了没、赚没赚」这三件事分散在第三、第四和最后一列——横向滚动
           的表格永远没法让它们同时在眼前。所以窄屏换一种排法：同一批 rows、同一个
           onRowClick，只是把一行摊成一张卡。
           这不是第二套列表——取数、筛选、分页仍然只有上面那一份，这里不持有任何状态。 -->
      <!-- 平板（≤1200px）也走这份卡片列表：iPad 竖屏减掉侧栏只剩 550 多像素，
           十一列照样要横滑。平板上排成两列网格，见样式里的 @media。 -->
      <!-- 桌面端的「卡片模式」也是这份列表，不另写一套：只是加上 m-grid 排成多列网格、
           封面放大成整张卡的头图（看图认货时比表格里 54px 的小缩略图好使得多）。 -->
      <div v-if="useCardList" v-loading="loading" class="m-list" :class="{ 'm-grid': gridMode }">
        <div v-for="row in rows" :key="row.row_key" class="m-card" @click="onRowClick(row)">
          <div class="m-top">
            <div class="cover m-cover">
              <img v-if="cover(row, gridMode ? 480 : 200)" :src="cover(row, gridMode ? 480 : 200)" alt="" loading="lazy" />
              <el-icon v-else class="cover-empty">
                <component :is="row.kind === 'device' ? 'Monitor' : 'Picture'" />
              </el-icon>
              <!-- 卡片模式下标签压在头图四角：左上类型（整机再跟上已售件数、归属人）、右上状态、
                   左下购入日。挪出正文区之后，显卡和整机的卡片正文就是同一种
                   结构，高度才统一得起来。 -->
              <template v-if="gridMode">
                <span class="m-corner m-corner--tl">
                  <PartTypeTag v-if="row.kind === 'part'" :type="row.part_type" />
                  <el-tag v-else size="small" effect="plain" :type="row.kind === 'device' ? 'warning' : 'primary'">
                    {{ t('inv.' + row.kind) }}
                  </el-tag>
                  <el-tag v-if="row.kind === 'device'" size="small" effect="plain" type="info" class="pcr-mono">
                    {{ row.sold_count }} / {{ row.part_count }}
                  </el-tag>
                  <el-tag v-if="row.owner" size="small" effect="dark" type="info" class="owner-tag">{{ row.owner }}</el-tag>
                </span>
                <span class="m-corner m-corner--tr"><StatusTag :status="row.status" /></span>
                <!-- 只给购入日：卡片是看图挑货用的，成交日在详情里看 -->
                <span v-if="row.purchase_date" class="m-corner m-corner--bl m-date pcr-mono">
                  {{ row.purchase_date }}
                </span>
              </template>
            </div>
            <div class="m-head">
              <div class="m-name">{{ nameOf(row) }}</div>
              <!-- 卡片模式下这一行就算是空的也占位，否则有副标题和没副标题的卡差一行高 -->
              <!-- 卡片模式不显示管理编号：看图挑货时用不上，占掉的位置留给副标题 -->
              <!-- 单列出来的部件在这一行标它来自哪台整机：点开进的是那台整机，不标的话
                   点完才发现打开的不是一张「卡」 -->
              <div v-if="row.parent" class="sub pcr-dim" :class="{ 'm-subline': gridMode }">
                {{ t('inv.partOf') }} <span class="pcr-mono">{{ row.parent.mgmt_no }}</span>
              </div>
              <div v-else-if="gridMode" class="sub pcr-dim m-subline">{{ row.subtitle }}</div>
              <div v-else-if="row.mgmt_no || row.subtitle" class="sub pcr-dim">
                <span class="pcr-mono">{{ row.mgmt_no }}</span>
                <template v-if="row.subtitle"> · {{ row.subtitle }}</template>
              </div>
              <div v-if="!gridMode" class="m-tags">
                <PartTypeTag v-if="row.kind === 'part'" :type="row.part_type" />
                <el-tag v-else size="small" effect="plain" :type="row.kind === 'device' ? 'warning' : 'primary'">
                  {{ t('inv.' + row.kind) }}
                </el-tag>
                <StatusTag :status="row.status" />
                <!-- 整机的「已售 / 总件数」：顶层行上最该先看到的就是它还剩几件没出手 -->
                <el-tag v-if="row.kind === 'device'" size="small" effect="plain" type="info" class="pcr-mono">
                  {{ row.sold_count }} / {{ row.part_count }}
                </el-tag>
                <el-tag v-if="row.owner" size="small" effect="dark" type="info" class="owner-tag">{{ row.owner }}</el-tag>
              </div>
            </div>
          </div>

          <!-- 成本 / 利润两个数并排（收回了多少不在卡片上给，利润已经把它算进去了）。桌面端成本上挂着「购入 + 国际运费 + 国内运费」
               的悬浮明细，这里不复刻：触屏没有悬浮，改成点一下弹层就和「点整行进详情」
               抢同一次点击，而详情页里那三项本来就是分行列着的。 -->
          <!-- 单列的部件没有单件成本、算不出利润（总价不往部件上摊），这两格换成它的售价 -->
          <div v-if="row.kind === 'part'" class="m-metrics">
            <div class="m-metric">
              <span class="m-label">{{ t('card.saleAmount') }}</span>
              <b class="pcr-mono">{{ money(row.sale_cny) }}</b>
            </div>
            <div class="m-metric">
              <span class="m-label">{{ t('card.saleDate') }}</span>
              <b class="pcr-mono">{{ row.sale_date }}</b>
            </div>
          </div>
          <div v-else class="m-metrics">
            <div class="m-metric">
              <span class="m-label">{{ t('card.cost') }}</span>
              <b class="pcr-mono">{{ money(row.cost_total_cny) }}</b>
              <!-- 日元成本压在人民币下面。货是在日站买的，对着成交页复核时看的是这个数；
                   两者是同一笔账的两种说法，不是两套口径（见 cards._to_jpy） -->
              <span class="m-sub pcr-mono pcr-dim">{{ money(row.cost_total_jpy, jpy) }}</span>
            </div>
            <div class="m-metric">
              <span class="m-label">{{ t('card.profit') }}</span>
              <b class="pcr-mono" :class="profitClass(row.profit_cny)">
                {{ money(row.profit_cny) }}
                <el-icon v-if="row.incomplete" class="warn-icon"><WarningFilled /></el-icon>
              </b>
            </div>
          </div>

          <div class="m-foot">
            <!-- 卡片模式下日期挪到了头图左下角，这里只剩「部件一览」按钮。
                 列表模式下左边购入日。 -->
            <template v-if="!gridMode">
              <span class="pcr-mono pcr-dim">{{ row.purchase_date }}</span>
            </template>
            <!-- 部件明细弹出来看，不在卡片里就地展开：网格里一张卡展开会把同一行的格子
                 撑得高低不齐，懒加载的列表里展开又会把下面的卡整片往下推。 -->
            <button v-if="row.children && row.children.length" class="m-expand" type="button"
              @click.stop="openParts(row)">
              {{ t('device.partsOverview') }}
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
        </div>
        <el-empty v-if="!rows.length && !loading" :description="t('common.noData')" :image-size="70" />
        <!-- 懒加载的触发点：滚到离它不远时取下一页。同时兼当底部状态行——
             「已经到底了」必须明说，否则人会以为是没加载出来、继续往下拉。 -->
        <div v-if="rows.length" ref="sentinel" class="m-more pcr-dim">
          <template v-if="loadingMore">{{ t('common.loading') }}</template>
          <template v-else-if="!hasMore">{{ t('inv.allLoaded', { n: total }) }}</template>
        </div>
      </div>

      <el-table
        v-else
        v-loading="loading"
        :data="rows"
        class="cards-table"
        row-key="row_key"
        :tree-props="{ children: 'children' }"
        :row-class-name="rowClass"
        @row-click="onRowClick"
      >
        <el-table-column :label="t('card.cover')" width="110">
          <template #default="{ row }">
            <!-- 二级行（部件）没有封面，这一格留空——树形展开的箭头和缩进由 el-table
                 画在第一列里，所以这一列要比原来宽一点 -->
            <!-- 单列出来的部件（row.solo）是顶层行，照样给封面，用的是部件自己的图 -->
            <div v-if="row.kind !== 'part' || row.solo" class="cover">
              <img v-if="cover(row)" :src="cover(row)" alt="" loading="lazy" />
              <el-icon v-else class="cover-empty">
                <component :is="row.kind === 'device' ? 'Monitor' : 'Picture'" />
              </el-icon>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('inv.kind')" width="90">
          <template #default="{ row }">
            <!-- 顶层行显示显卡 / 整机，二级行显示这个部件是什么（CPU / 内存…）。
                 部件那一套颜色在 PartTypeTag 里，整机详情的部件表用的是同一个组件 -->
            <PartTypeTag v-if="row.kind === 'part'" :type="row.part_type" />
            <el-tag v-else size="small" effect="plain" :type="row.kind === 'device' ? 'warning' : 'primary'">
              {{ t('inv.' + row.kind) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('inv.name')" min-width="190">
          <template #default="{ row }">
            <div class="model-cell">
              <span class="model-name">{{ nameOf(row) }}</span>
              <span v-if="row.parent" class="pcr-dim sub">
                {{ t('inv.partOf') }} <span class="pcr-mono">{{ row.parent.mgmt_no }}</span>
              </span>
              <span v-else-if="row.mgmt_no || row.subtitle" class="pcr-dim sub">
                <span class="pcr-mono">{{ row.mgmt_no }}</span>
                <template v-if="row.subtitle"> · {{ row.subtitle }}</template>
              </span>
            </div>
          </template>
        </el-table-column>
        <el-table-column :label="t('card.status')" width="110">
          <template #default="{ row }">
            <!-- 部件行也照实显示详情页里选的那个状态，不再按「有没有售价」改写成未出售——
                 状态是用户手选的，列表擅自换掉它就和详情页对不上了。只有老数据没存状态时才兜底 -->
            <StatusTag v-if="row.status" :status="row.status" />
            <el-tag v-else size="small" type="info" effect="plain">{{ t('device.unsold') }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('owner.label')" width="96">
          <template #default="{ row }">
            <!-- 部件跟随整机的归属人时压暗：真正需要一眼看到的是「这一件归了别人」 -->
            <span :class="{ 'pcr-dim': row.kind === 'part' && !row.owner_own }">{{ row.owner }}</span>
          </template>
        </el-table-column>
        <!-- 没有就空着，不画「—」：这张表里空白只有一个意思——这一格本来就没有数据。
             整张表都按这条来（见下面的 money()），一列破折号只是噪音。 -->
        <el-table-column :label="t('card.purchaseDate')" width="120">
          <template #default="{ row }"><span class="pcr-mono pcr-dim">{{ row.purchase_date }}</span></template>
        </el-table-column>
        <el-table-column :label="t('card.saleDate')" width="120">
          <template #default="{ row }">
            <!-- 整机这一格空着：部件是分批卖的，「最后成交那天」既不是这台机器卖完的
                 日子，也对不上任何一件的成交日，摆在顶层行上只会被当成前者。逐件的
                 出售日期在展开后的二级行上，那才是实情。 -->
            <span v-if="row.kind !== 'device'" class="pcr-mono pcr-dim">{{ row.sale_date }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('device.partsCount')" width="96" align="center">
          <template #default="{ row }">
            <!-- 只有整机这一格有意义：显卡就是一件，部件行本身也不再分件。
                 不适用就空着——「0 / 0」和「—」都会让人以为这里该有个数。 -->
            <span v-if="row.kind === 'device'" class="pcr-mono">{{ row.sold_count }} / {{ row.part_count }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('card.cost')" width="140" align="right">
          <template #default="{ row }">
            <!-- 部件这一格空着：没有单件成本（整机是一口价买的，总价不往部件上摊） -->
            <template v-if="row.kind !== 'part'">
              <!-- 总成本 = 购入价 + 国际运费 + 国内运费。三项都已计入合计，悬浮摊开是
                   为了让人一眼确认运费确实算进去了，而不是只看到一个总数在那儿。 -->
              <el-tooltip placement="left">
                <template #content>
                  <div class="cost-tip">
                    <div><span>{{ t('card.purchaseAmount') }}</span><b>{{ money(row.purchase_cny) }}</b></div>
                    <div><span>{{ t('card.intlShipping') }}</span><b>{{ money(row.intl_shipping_cny) }}</b></div>
                    <div><span>{{ t('card.domesticShipping') }}</span><b>{{ money(row.domestic_shipping_cny) }}</b></div>
                    <div class="cost-tip-sum"><span>{{ t('card.cost') }}</span><b>{{ money(row.cost_total_cny) }}</b></div>
                  </div>
                </template>
                <span class="pcr-mono cost-value">{{ money(row.cost_total_cny) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <!-- 日元成本单独一列，挨着人民币那列：货是在日本买的，对着日站的成交价复核时
             看日元才顺手。两列是同一笔账的两种说法（见 cards._to_jpy），不是两套口径——
             所以不再重复悬浮明细，明细挂在左边那一列上。 -->
        <el-table-column :label="t('inv.costJpy')" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row.kind !== 'part'" class="pcr-mono">{{ money(row.cost_total_jpy, jpy) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('device.revenue')" width="130" align="right">
          <template #default="{ row }">
            <!-- 这一列一律是**售价**，部件行也一样：国内运费已经算在「总成本」里了，
                 在这儿再标一次扣完运费的净收入，等于同一笔运费在一行里出现两遍，
                 看的人会去减第二次。二级行的售价加起来正好等于整机那一行。 -->
            <span class="pcr-mono">{{ money(row.sale_cny) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('card.profit')" width="150" align="right">
          <template #header>
            <!-- 这一列是净利润：收入减掉的成本里含国际运费与国内运费。表头标一下，
                 免得被当成「售价 − 购入价」的毛利去对账。 -->
            <el-tooltip :content="t('card.netProfitHint')">
              <span class="net-profit-head">{{ t('card.profit') }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <!-- 部件不算利润：成本不摊到单件，减不出来。这一格空着 -->
            <template v-if="row.kind !== 'part'">
              <span class="pcr-mono" :class="profitClass(row.profit_cny)">{{ money(row.profit_cny) }}</span>
              <el-tooltip v-if="row.incomplete" :content="t('card.incomplete')">
                <el-icon class="warn-icon"><WarningFilled /></el-icon>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
        <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
      </el-table>

      <!-- 卡片列表（含手机 / 平板）不分页，向下滚动自动续页，见 loadMore() -->
      <div v-if="!useCardList" class="pager">
        <!-- 窄屏砍掉「共 N 条」和每页条数：整条分页器排不下一行，挤成两行之后翻页箭头
             会跑到第二行的两端，拇指够不着。页码数也从 7 收到 5。 -->
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50, 100]"
          :layout="isMobile ? 'prev, pager, next' : 'total, sizes, prev, pager, next'"
          :pager-count="isMobile ? 5 : 7"
          background
          @current-change="fetch"
          @size-change="fetch"
        />
      </div>
    </el-card>

    <!-- 部件一览弹窗：只看不改。改部件仍然去整机详情页——那里是唯一的编辑界面
         （自动保存、按 id 增量写部件都在那一套里），这里再摆一份可编辑的表单就是第二套。
         点一行直接跳进详情页里那个部件所在的标签。 -->
    <el-dialog v-model="partsVisible" :title="partsRow ? nameOf(partsRow) : ''" width="640px" align-center>
      <template v-if="partsRow">
        <div class="pd-summary">
          <span>{{ t('device.partsCount') }} <b class="pcr-mono">{{ partsRow.sold_count }} / {{ partsRow.part_count }}</b></span>
          <span>{{ t('device.revenue') }} <b class="pcr-mono">{{ money(partsRow.sale_cny) }}</b></span>
        </div>
        <div class="pd-list">
          <button v-for="part in partsRow.children" :key="part.row_key" type="button" class="pd-row"
            @click="openPart(part)">
            <PartTypeTag :type="part.part_type" />
            <span class="pd-name">
              {{ nameOf(part) }}<span v-if="part.quantity > 1" class="pcr-dim pcr-mono"> ×{{ part.quantity }}</span>
            </span>
            <StatusTag v-if="part.status" :status="part.status" />
            <el-tag v-else size="small" type="info" effect="plain">{{ t('device.unsold') }}</el-tag>
            <span class="pd-date pcr-mono pcr-dim">{{ part.sale_date }}</span>
            <span class="pd-money pcr-mono">{{ money(part.sale_cny) }}</span>
          </button>
        </div>
      </template>
      <template #footer>
        <el-button @click="partsVisible = false">{{ t('common.close') }}</el-button>
        <el-button type="primary" @click="openPartsDevice">{{ t('inv.openDevice') }}</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗：显卡 / 整机的详情（也就是编辑界面）浮在列表上，不再跳页面。
         开关完全跟着路由走（见 openTarget）：这里不调 done()，而是改地址，地址一变
         model-value 自己就落成 false，中间由路由守卫先把改动存完。
         Esc 不关：详情里的下拉、日期面板都用 Esc 收起，会连带把整个弹窗关掉。
         key 用 openKey：换成另一件时整个详情重建，不会带着上一件的表单状态。
         定高 + 垂直居中（高度在 App.vue 的 .pcr-detail-dialog）：弹窗自己不滚动，
         内容由 DetailShell 拆成模块页。 -->
    <el-dialog
      :model-value="!!openTarget"
      :before-close="closeDetail"
      :fullscreen="isMobile"
      :close-on-press-escape="false"
      width="min(1280px, 94vw)"
      align-center
      class="pcr-detail-dialog"
      append-to-body
    >
      <template v-if="openTarget">
        <DeviceDetail v-if="openTarget.kind === 'device'" :key="openKey" ref="detailRef"
          :id="openTarget.id" :tab="openTab" @close="closeDetail" />
        <CardDetail v-else :key="openKey" ref="detailRef" :id="openTarget.id" @close="closeDetail" />
      </template>
    </el-dialog>

    <!-- 新增什么：显卡还是整机。两者的录入方式根本不同（一进一出 vs 一笔买进、拆成
         部件分别卖），选错了只能删掉重来，所以这里摆两张把区别说清楚的卡片，
         而不是下拉菜单里两行长得一样的字。 -->
    <el-dialog v-model="addVisible" :title="t('inv.addPick')" width="520px" align-center>
      <div class="add-picker">
        <button
          v-for="opt in ADD_OPTIONS"
          :key="opt.kind"
          class="add-option"
          type="button"
          :disabled="adding"
          :style="{ '--opt-color': opt.color }"
          @click="onAdd(opt.kind)"
        >
          <el-icon class="add-option-icon"><component :is="opt.icon" /></el-icon>
          <span class="add-option-title">{{ t(opt.label) }}</span>
          <span class="add-option-desc">{{ t(opt.desc) }}</span>
        </button>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onActivated, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowDown, ArrowRight, ArrowUp, Cpu, Filter, Grid, List, Monitor, Plus, Refresh, Search, WarningFilled
} from '@element-plus/icons-vue'
import { cardsApi, devicesApi, inventoryApi } from '@/api'
import { cny, firstImage, jpy, profitClass } from '@/utils/format'
import { ElMessage } from '@/utils/notify'
import { useIsCompact, useIsMobile, useIsTouch } from '@/composables/useIsMobile'
import { usePlatforms } from '@/composables/usePlatforms'
import { useMetaStore } from '@/stores/meta'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import StatusSelect from '@/components/StatusSelect.vue'
import FacetLabel from '@/components/FacetLabel.vue'
import PartTypeTag from '@/components/PartTypeTag.vue'
// 静态引入而不是 defineAsyncComponent：要拿 ref 调它们暴露的 beforeClose，
// 异步组件包了一层壳，ref 拿到的是壳，调不到里面
import CardDetail from '@/views/CardDetail/index.vue'
import DeviceDetail from '@/views/DeviceDetail/index.vue'

defineOptions({ name: 'Cards' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const meta = useMetaStore()
const { isMobile } = useIsMobile()
const { isCompact } = useIsCompact()
const { isTouch } = useIsTouch()

const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)

// 归属人筛选里「未指定」的取值，与后端 inventory_api.OWNER_NONE 同一个记号
const OWNER_NONE = '__none__'

// ── 联动的下拉选项 ──────────────────────────────────────────────────────
// 每个下拉的取值与件数都由后端按当前其余筛选算好（/inventory/facets），前端不自己
// 维护任何一份候选清单——自己维护的那份不会随着别的筛选变化，也就谈不上联动。
const facets = ref({})

// 已选的值即使在当前条件下一件都没有了，也要留在选项里（件数 0）：el-select 找不到
// 对应选项时，输入框里显示的是裸 value，多选的标签更会变成一串看不懂的 key。
function facetOptions(key, selected) {
  const list = facets.value[key] || []
  const have = new Set(list.map((o) => o.value))
  const picked = (Array.isArray(selected) ? selected : [selected]).filter((v) => v && !have.has(v))
  return list.concat(picked.map((value) => ({ value, count: 0 })))
}
function facetValues(key, selected) {
  return facetOptions(key, selected).map((o) => o.value)
}
function facetCounts(key) {
  return Object.fromEntries((facets.value[key] || []).map((o) => [o.value, o.count]))
}

const kindOptions = computed(() => facetOptions('kind', filters.kind))
const kindGoods = computed(() => kindOptions.value.filter((o) => !o.value.startsWith('part')))
const kindParts = computed(() => kindOptions.value.filter((o) => o.value.startsWith('part')))
function kindLabel(value) {
  if (value === 'part') return t('inv.allParts')
  if (value.startsWith('part:')) return t('partType.' + value.slice(5))
  return t('inv.' + value)
}
function ownerLabel(value) {
  return value === OWNER_NONE ? t('owner.none') : value
}

// 第二排那三个固定取值的下拉，选项同样来自 facets（件数为 0 的不出现）
const DERIVED_SELECTS = [
  { key: 'stock', placeholder: 'inv.stock', labels: { in_stock: 'inv.stockIn', settled: 'inv.settled' } },
  {
    key: 'profit',
    placeholder: 'inv.profitState',
    labels: { gain: 'inv.gain', loss: 'inv.loss', incomplete: 'inv.incomplete' }
  },
  { key: 'pool', placeholder: 'card.poolDraw', labels: { drawn: 'inv.poolDrawn', undrawn: 'inv.poolUndrawn' } }
]

// 只认最后一次请求的结果：筛选连着改几下时，先发的请求可能后回来，
// 拿旧条件算的选项盖掉新的，下拉里就会出现选了也筛不出东西的值。
let facetSeq = 0
async function fetchFacets() {
  const seq = ++facetSeq
  try {
    const res = await inventoryApi.facets(filterParams())
    if (seq === facetSeq && res && typeof res === 'object') facets.value = res
  } catch { /* 拦截器已提示；保留上一份选项 */ }
}

const blankFilters = () => ({
  keyword: '', kind: null, status: [], brand: null, model: null, source_platform: null, owner: [],
  stock: null, profit: null, pool: null, costMin: null, costMax: null
})
const filters = reactive(blankFilters())
// 购入 / 出售日期区间：绑定 daterange 选择器，拆成 *_from / *_to 传后端
const dateRange = ref(null)
const saleRange = ref(null)

// 窄屏上除搜索框外的筛选器收在开关后面，只影响显示，不参与取数
const filtersOpen = ref(false)
// 宽屏上第二排（按算出来的值筛的那几项）收在「更多筛选」后面
const moreOpen = ref(false)
const moreFilterCount = computed(() => {
  const f = filters
  return [saleRange.value, f.stock, f.profit, f.pool, f.costMin != null || f.costMax != null]
    .filter(Boolean).length
})
// 开关按钮上的角标。不含关键词——搜索框一直摆在外面，它有没有值本来就看得见；
// 收起来的那几项才需要这个数提醒「现在看到的不是全部」。
const activeFilterCount = computed(() => {
  const f = filters
  return [f.kind, f.status.length, f.brand, f.model, f.source_platform, f.owner.length, dateRange.value]
    .filter(Boolean).length + moreFilterCount.value
})

// 手机上那两个单日期选择器写回同一个区间 ref。两头都清空时整个置回 null，
// 而不是留一个 [null, null]——filterParams 取的是 ?.[0] / ?.[1]，留着不影响取数，
// 但「筛选」角标数的是区间本身真不真，留着会一直显示有一项筛选在生效。
function setRangeEnd(range, i, value) {
  const next = [range.value?.[0] || null, range.value?.[1] || null]
  next[i] = value || null
  range.value = next[0] || next[1] ? next : null
  reload()
}

// 宽屏下的排法：表格或卡片。记在本机浏览器里——这是个人的看法偏好，不是数据，
// 不值得进 app_settings 让所有人共用一份。存取都包 try：隐私模式下 localStorage
// 可能直接抛错，那时退回表格即可，不能让整页挂掉。
const VIEW_MODE_KEY = 'pcr_cards_view_mode'
function readViewMode() {
  try { return localStorage.getItem(VIEW_MODE_KEY) === 'cards' ? 'cards' : 'table' } catch { return 'table' }
}
const viewMode = ref(readViewMode())
watch(viewMode, (v) => {
  try { localStorage.setItem(VIEW_MODE_KEY, v) } catch { /* 记不住就算了 */ }
})
// 紧凑宽度以下永远是卡片列表（与开关无关）；宽屏选了卡片模式时排成网格大图
const gridMode = computed(() => !isCompact.value && viewMode.value === 'cards')
const useCardList = computed(() => isCompact.value || gridMode.value)

// 部件一览弹窗当前展示的那台整机（列表里那一行本身，children 就是部件）
const partsVisible = ref(false)
const partsRow = ref(null)
function openParts(row) {
  partsRow.value = row
  partsVisible.value = true
}
function openPartsDevice() {
  partsVisible.value = false
  openDetail('device', partsRow.value.id)
}
// 带上部件类型，详情落地就停在这个部件那一页，省得进去再找一遍
function openPart(part) {
  partsVisible.value = false
  openDetail('device', part.device_id, part.part_type)
}

const emptyStats = () => ({
  total: 0, cards: 0, devices: 0, parts: 0, in_stock: 0, settled: 0,
  total_cost_cny: 0, total_cost_jpy: 0, total_revenue_cny: 0, total_profit_cny: 0,
  recovery: null, incomplete: 0
})
const stats = ref(emptyStats())
const statsLoading = ref(false)

const { platformLabel } = usePlatforms()

// 顶部统计卡。顺序固定：先数量、后金额，颜色跟着指标走，不随数值变化重排
const statCards = computed(() => {
  const s = stats.value
  const profit = s.total_profit_cny
  return [
    // 按状态筛时会有从整机里单独列出来的部件，它们只算件数、不进金额合计，在这里说一声
    { key: 'total', label: t('inv.total'), value: s.total, sub: s.parts ? t('inv.partsIncluded', { n: s.parts }) : undefined, icon: 'Box', color: '#409EFF' },
    { key: 'cards', label: t('inv.cards'), value: s.cards, icon: 'Cpu', color: '#5b8cff' },
    { key: 'devices', label: t('inv.devices'), value: s.devices, icon: 'Monitor', color: '#E6A23C' },
    { key: 'inStock', label: t('dashboard.inStock'), value: s.in_stock, icon: 'Goods', color: '#a78bfa' },
    { key: 'settled', label: t('inv.settled'), value: s.settled, icon: 'Sell', color: '#67C23A' },
    {
      key: 'cost',
      label: t('dashboard.totalCost'),
      value: cny(s.total_cost_cny),
      // 与列表里每一行同样的处理：日元是参考口径，压在主数字下面
      sub: jpy(s.total_cost_jpy),
      icon: 'Coin',
      color: '#F56C6C'
    },
    { key: 'revenue', label: t('dashboard.totalRevenue'), value: cny(s.total_revenue_cny), icon: 'Money', color: '#38bdf8' },
    {
      key: 'profit',
      label: t('dashboard.totalProfit'),
      value: cny(profit),
      icon: 'TrendCharts',
      color: profit > 0 ? '#67C23A' : profit < 0 ? '#F56C6C' : '#409EFF',
      valueClass: profitClass(profit)
    }
  ]
})

// 表格里的金额：没有就空着，不摆「—」。空白在这张表里只有一个意思——这一格本来就
// 没有数据（还没卖、部件不摊成本）；真正算不出来的那种（缺汇率）由「利润」列右边的
// 警告图标标着，不靠破折号传达。
function money(value, fmt = cny) {
  return value === null || value === undefined ? '' : fmt(value)
}



// 二级行（部件）整行淡一档，一眼能看出层级
// 单列出来的部件是顶层行，不压暗
const rowClass = ({ row }) => (row.kind === 'part' && !row.solo ? 'part-row' : '')

// 图床按 w 参数出缩略图。卡片模式的头图有 300px 上下宽，再拿 200 的图拉伸会糊
function cover(row, width = 200) {
  const img = firstImage(row.media)
  if (!img || img.kind !== 'image') return null
  return img.public_url + (img.public_url.includes('?') ? '&' : '?') + 'w=' + width
}
function nameOf(row) {
  if (row.title) return row.title
  if (row.kind === 'device') return t('device.noTitle')
  if (row.kind === 'part') return t('partType.' + row.part_type)
  return t('card.noModel')
}

// 列表和统计共用的筛选参数
function filterParams() {
  return {
    keyword: filters.keyword || undefined,
    // 部件类型在下拉里编成 part:cpu 这样一个值，传给后端时拆成 kind + part_type
    kind: filters.kind ? filters.kind.split(':')[0] : undefined,
    part_type: filters.kind?.startsWith('part:') ? filters.kind.slice(5) : undefined,
    status: filters.status.length ? filters.status.join(',') : undefined,
    brand: filters.brand || undefined,
    model: filters.model || undefined,
    source_platform: filters.source_platform || undefined,
    purchase_from: dateRange.value?.[0] || undefined,
    purchase_to: dateRange.value?.[1] || undefined,
    owner: filters.owner.length ? filters.owner.join(',') : undefined,
    sale_from: saleRange.value?.[0] || undefined,
    sale_to: saleRange.value?.[1] || undefined,
    stock: filters.stock || undefined,
    profit: filters.profit || undefined,
    pool: filters.pool || undefined,
    // 0 是合法的下限，不能用 || 判空
    cost_min: filters.costMin ?? undefined,
    cost_max: filters.costMax ?? undefined
  }
}

// 每次整表重取自增一次。续页请求发出时记下当时的值，回来时对不上就丢弃——
// 否则「滚到底触发续页 → 立刻改了筛选」会把旧筛选的下一页拼到新结果后面。
let fetchSeq = 0

// 后端 page_size 的上限（inventory_api.list 的 le=200）
const MAX_PAGE_SIZE = 200

async function fetch() {
  const seq = ++fetchSeq
  loading.value = true
  // 卡片列表是「前 page 页拼起来」的，刷新时一次取回这么多条，而不是只取第 page 页：
  // 从详情页返回时要刷新数据，但不能把已经滚出来的几页清掉、让人从头再滚一遍。
  // 超过后端上限就只保留能取回的那些，page 按实际条数折回去，续页从那里接着走。
  const params = useCardList.value
    ? { page: 1, page_size: Math.min(page.value * pageSize.value, MAX_PAGE_SIZE) }
    : { page: page.value, page_size: pageSize.value }
  try {
    const res = await inventoryApi.list({ ...filterParams(), ...params })
    if (seq !== fetchSeq) return
    // 请求成功但形状不对，几乎只有一种原因：拿到的根本不是这个接口的响应（后端没重启、
    // 接口不存在时曾经会回一整页 HTML）。必须显式报出来——退化成一张「暂无数据」的空表
    // 是最难查的那种失败：页面看着好好的，数据却凭空消失了。
    if (!res || !Array.isArray(res.items) || typeof res.total !== 'number') {
      rows.value = []
      total.value = 0
      ElMessage.error(t('common.badResponse'))
      return
    }
    rows.value = res.items
    total.value = res.total
    if (useCardList.value) page.value = Math.max(1, Math.ceil(res.items.length / pageSize.value))
  } finally {
    if (seq === fetchSeq) loading.value = false
  }
  fetchStats()
  fetchFacets()
  recheckSentinel()
}

// ── 卡片列表的懒加载 ────────────────────────────────────────────────────
const loadingMore = ref(false)
const hasMore = computed(() => rows.value.length < total.value)

async function loadMore() {
  if (!useCardList.value || loading.value || loadingMore.value || !hasMore.value) return
  const seq = fetchSeq
  loadingMore.value = true
  try {
    const res = await inventoryApi.list({ ...filterParams(), page: page.value + 1, page_size: pageSize.value })
    if (seq !== fetchSeq || !Array.isArray(res?.items)) return
    // 两次请求之间有人新增 / 卖出了东西，分页边界会挪一格，同一行可能在两页里各出现
    // 一次。按 row_key 去重——v-for 的 key 重复时 Vue 会把两张卡渲染成同一张。
    const seen = new Set(rows.value.map((r) => r.row_key))
    rows.value = rows.value.concat(res.items.filter((r) => !seen.has(r.row_key)))
    total.value = res.total
    page.value += 1
  } catch { /* 拦截器已提示；再往下滚会重试 */ } finally {
    loadingMore.value = false
  }
  recheckSentinel()
}

// 滚动容器是 Layout 里的 .main（overflow-y: auto），不是整个视口。观察器的 root
// 必须是它：以视口为 root 时，rootMargin 的提前量会被 .main 的裁剪吃掉，
// 只有真滚到最底才触发，每次都要停下来等一拍。
const sentinel = ref(null)
let observer = null
function scrollParentOf(el) {
  for (let p = el.parentElement; p; p = p.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(p).overflowY)) return p
  }
  return null
}
watch(sentinel, (el) => {
  observer?.disconnect()
  observer = null
  if (!el) return
  observer = new IntersectionObserver(
    (entries) => { if (entries.some((e) => e.isIntersecting)) loadMore() },
    { root: scrollParentOf(el), rootMargin: '0px 0px 600px 0px' }
  )
  observer.observe(el)
})
// 观察器只在「进入 / 离开」时回调。一页加载完触发点仍在可视范围里（大屏一页铺不满，
// 或者筛选后结果很少）就不会再有回调，列表停在半截。每次取完数重新挂一次，
// 挂上时观察器会按当前位置补发一次回调，由它决定要不要接着取。
async function recheckSentinel() {
  await nextTick()
  if (observer && sentinel.value) {
    observer.unobserve(sentinel.value)
    observer.observe(sentinel.value)
  }
}
onBeforeUnmount(() => observer?.disconnect())

// 表格 ↔ 卡片切换时从第一页重来：两边对 page 的理解不同（表格是「第几页」，
// 卡片是「已经拼了几页」），带着旧值过去，表格会停在第 5 页、卡片会只剩第 5 页那 20 条。
watch(useCardList, () => reload())

async function fetchStats() {
  statsLoading.value = true
  try {
    const res = await inventoryApi.stats(filterParams())
    // 同上：形状不对就退回全 0，而不是把一个字段全是 undefined 的东西摆上去
    // ——那样每个指标都显示成「—」，看着像「没数据」，其实是响应根本不对。
    stats.value = typeof res?.total === 'number' ? res : emptyStats()
  } catch {
    stats.value = emptyStats()
  } finally {
    statsLoading.value = false
  }
}

function reload() {
  page.value = 1
  fetch()
}
function resetFilters() {
  Object.assign(filters, blankFilters())
  dateRange.value = null
  saleRange.value = null
  reload()
}

async function loadAux() {
  await meta.ensure()
}

// 新增 = 先建一行空草稿，再进详情页填。详情页本身就是编辑界面，没有第二套「新增
// 表单」要维护；草稿不进列表也不进统计，什么都没填就离开的话详情页会把它删掉。
// 新增弹窗的两张卡片。图标与颜色跟顶部统计卡里的「显卡」「整机」一致——
// 同一个东西在一个页面里换个地方就换套长相，只会让人多认一遍。
const ADD_OPTIONS = [
  { kind: 'card', icon: Cpu, color: '#5b8cff', label: 'inv.addCard', desc: 'inv.addCardDesc' },
  { kind: 'device', icon: Monitor, color: '#E6A23C', label: 'inv.addDevice', desc: 'inv.addDeviceDesc' }
]

const addVisible = ref(false)
const adding = ref(false)

// 建一行空草稿再跳进详情页（见 CLAUDE.md 的「草稿行」）。建的过程中把两张卡片禁掉：
// 手快点两下会建出两行草稿，其中一行没人管，只能等两小时后被清理掉。
async function onAdd(kind) {
  if (adding.value) return
  adding.value = true
  try {
    const draft = kind === 'device' ? await devicesApi.createDraft() : await cardsApi.createDraft()
    addVisible.value = false
    openDetail(kind, draft.id)
  } catch { /* 拦截器已提示 */ } finally {
    adding.value = false
  }
}

// 点一行就弹出它的详情——看和改都在那里。部件行弹的是它所属的那台整机：部件是整机
// 的一部分，没有自己的详情。
function onRowClick(row) {
  if (row.kind === 'part') return openDetail('device', row.device_id, row.part_type)
  openDetail(row.kind, row.id)
}

// ── 详情弹窗 ──────────────────────────────────────────────────────────
// 开着哪一件记在地址栏的 ?open=card-12 / device-5 里，而不是一个本地 ref：
// 这样手机的返回键 / 浏览器后退关掉的是弹窗而不是整个列表页，刷新后还开着同一件，
// 链接也能直接发给别人。弹窗开关因此只有一个事实来源——路由。
const detailRef = ref(null)
const openKey = computed(() => (route.name === 'Cards' ? String(route.query.open || '') : ''))
const openTarget = computed(() => {
  const m = /^(card|device)-(\d+)$/.exec(openKey.value)
  return m ? { kind: m[1], id: Number(m[2]) } : null
})
const openTab = computed(() => (route.query.tab ? String(route.query.tab) : null))

// push 而不是 replace：要留下一条历史记录，后退键才有东西可退
function openDetail(kind, id, tab = null) {
  router.push({ query: { open: `${kind}-${id}`, ...(tab ? { tab } : {}) } })
}
// 关闭优先走「后退」：弹窗是从列表上 push 出来的，后退正好回到那一条，历史里不会
// 越积越多的「列表 → 详情 → 列表 → 详情」。直接打开的链接（前一条不是列表）没得退，
// 才 replace 掉 open 参数。
function closeDetail() {
  const back = window.history.state?.back
  const prev = back ? router.resolve(back) : null
  if (prev && prev.name === 'Cards' && !prev.query.open) router.back()
  else router.replace({ query: {} })
}

// 弹窗关掉之前必须把详情里没落盘的改动存完、空草稿删掉（详情的 beforeClose）。
// 关掉它的路径有好几条——关闭按钮、点遮罩、后退键、点侧栏去别的页——全都是路由
// 变化，所以统一在路由守卫里 await，哪条路走过来都漏不掉。
async function settleDetail(to, from) {
  const leaving = to.name !== 'Cards' || to.query.open !== from.query.open
  if (from.query.open && leaving) await detailRef.value?.beforeClose?.()
}
onBeforeRouteUpdate(settleDetail)
onBeforeRouteLeave(settleDetail)

// 弹窗关上（或者换成另一件）后刷新列表：刚才改的价钱、状态、封面得反映到卡片上。
// fetch 在卡片列表下会一次取回已滚出来的那几页，滚动位置不会丢。
// 点侧栏去了别的页也会让 openKey 变空，那时列表页已经被 keep-alive 收起来，不用白取一遍
//（回来时 onActivated 会取）。
watch(openKey, (now, before) => {
  if (before && now !== before && route.name === 'Cards') fetch()
})

// 概览页点进来时带 ?status=xxx，直接把筛选摆好；带空的 status= 表示「看全部」。
// 判断的是「有没有这个参数」而不是它真不真：从详情页返回时 query 是空的，
// 那种情况下必须原样保留用户自己设的筛选，不能顺手清掉。
function applyRouteQuery() {
  if (!('status' in route.query)) return
  const status = route.query.status
  filters.status = String(status || '').split(',').filter(Boolean)
  page.value = 1
}

onActivated(() => {
  applyRouteQuery()
  loadAux()
  fetch()
})
</script>

<style scoped>
/* 成本上有明细可看：加条虚下划线提示可以悬浮，否则没人会想到把鼠标停上去 */
.cost-value { border-bottom: 1px dotted #5a6478; cursor: help; }
.net-profit-head { border-bottom: 1px dotted #5a6478; cursor: help; }
.cost-tip div { display: flex; justify-content: space-between; gap: 18px; line-height: 1.9; }
.cost-tip b { font-variant-numeric: tabular-nums; }
.cost-tip-sum { border-top: 1px solid rgba(255, 255, 255, 0.2); margin-top: 4px; padding-top: 4px; }
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title { font-size: 20px; }

/* 顶部统计卡（与 FreeMarket_Manager 库存页同一套版式） */
.stats-card { margin-bottom: 16px; border-radius: 8px; }
/* 换行后两排卡片之间的空隙由 el-col 的下边距给出；最后一排多出来的那 16px
   用行的负下边距抵掉，否则卡片和卡片底之间会比左右留白宽一截 */
.stat-row { margin-bottom: -16px; }
.stat-row :deep(.el-col) { margin-bottom: 16px; }
.stats-warn {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 16px;
  font-size: 12px;
  color: #f5a623;
}

.filter-card { margin-bottom: 16px; }
.filter-card :deep(.el-card__body) { padding: 14px 16px; }
.filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.f-keyword { width: 210px !important; }
.f-kind { width: 120px !important; }
.f-status { width: 190px !important; }
.f-brand { width: 150px !important; }
.f-model { width: 160px !important; }
.f-platform { width: 140px !important; }
.f-date { width: 250px !important; }
.f-owner { width: 170px !important; }
.owner-tag { max-width: 90px; overflow: hidden; text-overflow: ellipsis; }
.f-small { width: 130px !important; }
.f-cost { display: flex; align-items: center; gap: 6px; }
.f-cost-input { width: 110px !important; }
.f-cost-input :deep(input) { text-align: left; }
/* 第二排与第一排之间的空隙与同排控件的间距一致，看上去是同一组筛选换了行 */
.filters-more { margin-top: 10px; }
/* 角标做成贴在文字后面的小圆点，不用 el-badge：badge 是绝对定位的，
   在按钮里会跑到边框外面被相邻控件盖住 */
.f-count {
  margin-left: 5px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--pcr-accent);
  color: #fff;
  font-size: 11px;
  line-height: 16px;
  text-align: center;
}

.cards-table :deep(.el-table__row) { cursor: pointer; }
/* 二级行（部件）压暗一档并留出缩进，和顶层行分得开 */
.cards-table :deep(.part-row) { background: rgba(91, 140, 255, 0.03); }
.cards-table :deep(.part-row .cell) { color: #b9c4d6; }
/* 树形展开箭头是 el-table 画在第一列单元格里的行内元素，而封面是个块级盒子——
   不排成一行的话，箭头会被顶到封面上面去。占位符和箭头统一宽度，让有子行和没子行
   的封面左边缘对齐。 */
.cards-table :deep(td.el-table__cell:first-child .cell) {
  display: flex;
  align-items: center;
  gap: 6px;
}
.cards-table :deep(td.el-table__cell:first-child .cell > *) { flex: none; }
.cards-table :deep(td.el-table__cell:first-child .el-table__expand-icon),
.cards-table :deep(td.el-table__cell:first-child .el-table__placeholder) { width: 22px; }
.cover {
  width: 54px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  background: #0e1830;
  display: flex;
  align-items: center;
  justify-content: center;
}
.cover img { width: 100%; height: 100%; object-fit: cover; }
.cover-empty { color: #3a4a66; font-size: 18px; }
.model-cell { display: flex; flex-direction: column; }
.model-name { color: #e6edf7; }
.sub { font-size: 12px; }
.warn-icon { color: #f5a623; margin-left: 4px; vertical-align: middle; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }

/* ── 新增弹窗里的两张卡片 ──────────────────────────────────────────────
   用原生 button 而不是 div：键盘能 Tab 到、能回车按下、禁用态是浏览器原生的，
   这些在 div 上都得自己补一遍。 */
.add-picker { display: flex; gap: 12px; }
.add-option {
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 18px 16px;
  border: 1px solid var(--pcr-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  color: var(--pcr-text);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}
.add-option:hover:not(:disabled),
.add-option:focus-visible {
  /* 边框与图标本来就是这一类的代表色，悬浮时把边框点亮即可，不另配一套高亮色 */
  border-color: var(--opt-color);
  background: rgba(255, 255, 255, 0.05);
  outline: none;
}
.add-option:disabled { opacity: 0.6; cursor: default; }
.add-option-icon { font-size: 24px; color: var(--opt-color); }
.add-option-title { font-size: 15px; font-weight: 600; }
.add-option-desc { font-size: 12px; line-height: 1.5; color: var(--pcr-text-dim); }

/* ── 手机卡片列表 ──────────────────────────────────────────────────────
   一行摊成一张卡：上半是「这是什么」（封面 / 名称 / 类型 / 状态），中间一排是三个钱
   （成本 / 收入 / 利润），底下一行是日期。顺序照着人拿起手机想知道的顺序排，
   不是照桌面端的列序。 */
.m-list { display: flex; flex-direction: column; gap: 10px; }
.m-card {
  padding: 12px;
  border: 1px solid var(--pcr-border);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.015);
}
/* 按下去给一下反馈。整张卡都是点击区（全局关掉了 tap 高亮），不给反馈的话
   点完到路由跳转之间那一下会让人以为没点着，于是又点一次 */
.m-card:active { background: rgba(91, 140, 255, 0.08); }
.m-top { display: flex; gap: 10px; align-items: flex-start; }
/* 封面比桌面端大一档：手机上这张图常常是认出「哪张卡」最快的线索 */
.m-cover { width: 72px; height: 54px; flex: none; }
.m-head { flex: 1 1 auto; min-width: 0; }
.m-name { color: #e6edf7; font-size: 15px; font-weight: 500; line-height: 1.35; }
.m-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }

.m-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--pcr-border);
}
.m-metric { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.m-label { font-size: 11px; color: #8a94a6; }
/* 三个数都用等宽数字：三列上下对不齐的话，扫一眼看不出哪个大 */
.m-metric b { font-size: 15px; font-weight: 600; color: #e6edf7; }
.m-metric .m-sub { font-size: 11px; }

.m-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  font-size: 12px;
}
/* 出资人靠右；后面若还有「部件一览」按钮，按钮仍贴在最右 */
/* 展开按钮挤到右端，和左边的日期分开——它是个能按的东西，不该混在日期里 */
.m-expand {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: rgba(91, 140, 255, 0.1);
  color: #8fb8ff;
  font-size: 12px;
}
/* ── 部件一览弹窗 ──────────────────────────────────────────────────── */
.pd-summary { display: flex; gap: 20px; margin-bottom: 12px; font-size: 13px; color: #8a94a6; }
.pd-summary b { color: #e6edf7; margin-left: 4px; }
.pd-list { display: flex; flex-direction: column; gap: 6px; max-height: 60vh; overflow-y: auto; }
/* 一行是一个按钮：点了跳进详情页里这个部件那一页，键盘也能 Tab 过去按 */
.pd-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: rgba(91, 140, 255, 0.04);
  color: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}
.pd-row:hover, .pd-row:focus-visible { border-color: rgba(91, 140, 255, 0.5); outline: none; }
.pd-name { flex: 1 1 auto; min-width: 0; color: #b9c4d6; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pd-date { flex: none; font-size: 12px; }
.pd-money { flex: none; min-width: 80px; text-align: right; color: #e6edf7; }

/* 平板：卡片两列排。一列的话每张卡被拉成 550～900px 宽，三个金额隔得老远，
   一屏只放得下三四张；两列正好是手机卡片的宽度，信息密度回到桌面表格的水平。
   align-items: start——展开了部件的那张变高时，同一行另一张不跟着被拉长。 */
@media (min-width: 769px) and (max-width: 1200px) {
  .m-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
    gap: 12px;
  }
  .m-list > .el-empty, .m-list > .m-more { grid-column: 1 / -1; }
}

/* ── 宽屏卡片模式 ──────────────────────────────────────────────────────
   同一份卡片，按宽度自动排列数；封面从左侧小图改成占满卡宽的 4:3 头图，
   名称和标签落到图下面。悬浮给个边框高亮——宽屏有鼠标，整张卡可点得让人看出来。 */
.f-view { margin-left: auto; }
/* 卡片大小统一：每张卡的正文都是同一套固定行高（名称两行、副标题一行、底栏一行），
   标签挪到了头图四角，所以显卡和整机摊开来是同一个高度。同一行里再由网格默认的
   stretch 拉齐，底栏靠 margin-top: auto 贴底，金额行、日期行落在同一水平线上。
   不用 grid-auto-rows: 1fr：那会把底部的「已全部加载」和空状态也撑成一张卡那么高。 */
.m-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 14px;
}
.m-grid > .el-empty, .m-grid > .m-more { grid-column: 1 / -1; }
.m-grid .m-card {
  display: flex;
  flex-direction: column;
  cursor: pointer;
  transition: border-color 0.15s, background-color 0.15s;
}
.m-grid .m-card:hover { border-color: rgba(91, 140, 255, 0.5); background: rgba(91, 140, 255, 0.04); }
.m-grid .m-top { flex-direction: column; gap: 10px; }
.m-grid .m-cover { position: relative; width: 100%; height: auto; aspect-ratio: 4 / 3; }
.m-grid .m-cover .cover-empty { font-size: 40px; }
.m-grid .m-head { width: 100%; }
.m-grid .m-name {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: calc(2 * 1.35em);
}
.m-grid .m-subline { min-height: 1.5em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
/* 底栏一律占一行：显卡没有「部件一览」按钮，整机没有成交日，内容不同但高度一样 */
.m-grid .m-foot { margin-top: auto; padding-top: 10px; min-height: 30px; }
.m-grid .m-metrics { margin-top: 10px; }

/* 头图四角的标签。图片底色深浅不定，给每个角垫一层深色底，
   描边样式的标签（底色透明）压在浅色图上也看得清 */
.m-corner {
  position: absolute;
  display: inline-flex;
  padding: 2px;
  border-radius: 12px;
  background: rgba(11, 18, 32, 0.72);
  backdrop-filter: blur(4px);
  line-height: 1;
}
.m-corner :deep(.el-tag--plain) { --el-tag-bg-color: transparent; }
.m-corner--tl { top: 8px; left: 8px; }
.m-corner--tr { top: 8px; right: 8px; }
.m-corner--br { bottom: 8px; right: 8px; }
.m-corner--bl { bottom: 8px; left: 8px; }
/* 左上角整机多一个件数标签，两个标签之间留点空 */
.m-corner--tl { gap: 4px; }
/* 右下角出资人名字可能有好几个，别让它压过左下角的日期 */
.m-corner--br { max-width: 55%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
/* 日期不是 el-tag，自己补上和标签差不多的内边距与字号，四个角看着是一套 */
.m-date { padding: 4px 8px; font-size: 11px; color: #c9d3e3; }

.m-more { padding: 14px 0 4px; text-align: center; font-size: 12px; min-height: 20px; }

/* 触屏：展开部件的按钮本来只有 28px 高，又紧挨着「点整张卡进详情」的区域，
   按偏一点就进了详情页 */
@media (hover: none) {
  .m-expand { padding: 9px 12px; font-size: 13px; }
}

@media (max-width: 768px) {
  /* 展开后的筛选器各占满一行——并排只会各自剩下小半个框，看不清选的是什么。
     搜索框是例外：它和「筛选」开关共一行，收起状态下这一行就是全部筛选界面。 */
  .f-kind, .f-status, .f-brand, .f-model, .f-platform, .f-owner, .f-date, .f-small { width: 100% !important; }
  .f-cost { width: 100%; }
  .f-cost-input { flex: 1 1 0; width: auto !important; }
  .filters { align-items: stretch; }
  .f-keyword { flex: 1 1 60%; width: auto !important; }
  .f-toggle { flex: 0 0 auto; margin-left: 0; }
  .f-add { flex: 1 1 100%; margin-left: 0; }
  /* 两张卡片并排在手机上只剩半屏宽，说明文字会碎成每行两三个字 */
  .add-picker { flex-direction: column; }
  /* 卡片列表自己带圆角和边框，外面那张卡的内边距只会白白吃掉两边各 12px */
  .table-card :deep(.el-card__body) { padding: 10px; }
  .pager { justify-content: center; }
  /* 弹窗在手机上只剩 330 来像素，五样东西排一行时名称会被挤没；成交日让出位置 */
  .pd-date { display: none; }
  .pd-money { min-width: 0; }
}
</style>
