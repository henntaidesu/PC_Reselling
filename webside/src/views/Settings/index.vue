<template>
  <div class="settings-page">
    <h2 class="page-title">{{ t('settings.title') }}</h2>

    <!-- 二级菜单：el-tabs 只当标签条用，内容在下面按 activeTab 自己渲染。
         挂进 el-tab-pane 的话五块会一次性全挂载，图床配置与数据库状态（含整库表清单）
         每次进页面都要白拉一遍——配 ensureSection 的按需加载，把这两发请求推迟到真点开 -->
    <div class="tabs-row">
      <el-tabs v-model="activeTab" class="settings-tabs">
        <el-tab-pane v-for="s in SECTIONS" :key="s.name" :name="s.name">
          <template #label>
            <span class="tab-label">
              <el-icon><component :is="s.icon" /></el-icon>{{ t(s.labelKey) }}
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- ── 图床 ──────────────────────────────────────────────────────── -->
    <template v-if="activeTab === 'hosting'">
      <el-card shadow="never" class="pane-card form-pane">
        <template #header>{{ t('settings.imageHosting') }}</template>
        <el-form label-width="150px" label-position="left">
          <el-form-item :label="t('settings.baseUrl')">
            <el-input v-model="hosting.base_url" />
          </el-form-item>
          <el-form-item :label="t('settings.publicBase')">
            <el-input v-model="hosting.public_base" />
          </el-form-item>
          <el-form-item :label="t('settings.project')">
            <el-input v-model="hosting.project" />
          </el-form-item>
          <el-form-item :label="t('settings.token')">
            <el-input v-model="hosting.token" type="password" show-password />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12">
              <el-form-item :label="t('settings.timeout')">
                <el-input-number v-model="hosting.timeout" :min="5" :max="600" :controls="false" class="full" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item :label="t('settings.verifyTls')" label-width="120px">
                <el-switch v-model="hosting.verify_tls" />
              </el-form-item>
            </el-col>
          </el-row>
          <div class="form-actions">
            <el-button type="primary" :loading="savingHosting" @click="saveHosting">{{ t('common.save') }}</el-button>
            <el-button :loading="testing" @click="testHosting">{{ t('settings.test') }}</el-button>
          </div>
          <el-alert v-if="testResult" :type="testResult.ok ? 'success' : 'error'" :closable="false" show-icon class="mt">
            <template v-if="testResult.ok">
              {{ t('settings.testOk') }} · {{ t('settings.allowedExt') }}: {{ (testResult.allowed_extensions || []).join(', ') }}
              <template v-if="testResult.max_upload_bytes"> · {{ t('settings.maxUpload') }}: {{ prettySize(testResult.max_upload_bytes) }}</template>
            </template>
            <template v-else>{{ testResult.message }}</template>
          </el-alert>
        </el-form>
      </el-card>
    </template>

    <!-- ── 数据库 ────────────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'db'">
      <el-row :gutter="16">
        <el-col :xs="24" :md="12">
          <el-card shadow="never" class="pane-card">
            <template #header>
              {{ t('settings.database') }}
              <el-tag :type="db.ok ? 'success' : 'danger'" effect="dark" size="small" class="head-tag">
                {{ db.ok ? t('settings.dbConnected') : t('settings.dbDisconnected') }}
              </el-tag>
            </template>
            <div class="kv"><span>{{ t('settings.dbConf') }}</span><b class="pcr-mono">{{ db.conf_path }}</b></div>
            <div class="kv"><span>{{ t('settings.dbHost') }}</span><b class="pcr-mono">{{ db.host }}:{{ db.port }}</b></div>
            <div class="kv"><span>{{ t('settings.dbName') }}</span><b class="pcr-mono">{{ db.database }}</b></div>
            <div class="kv"><span>{{ t('settings.dbUser') }}</span><b class="pcr-mono">{{ db.user }}</b></div>
            <div class="kv" v-if="db.version"><span>{{ t('settings.dbVersion') }}</span><b class="pcr-mono">{{ db.version }}</b></div>
            <div class="kv" v-if="db.error"><span class="pcr-loss">Error</span><b class="pcr-loss">{{ db.error }}</b></div>
            <div class="form-actions">
              <el-button :icon="Refresh" :loading="reconnecting" @click="reconnect">{{ t('settings.dbReconnect') }}</el-button>
            </div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="never" class="pane-card">
            <template #header>{{ t('settings.dbTables') }}</template>
            <el-table :data="db.tables || []" size="small" max-height="420">
              <el-table-column prop="name" :label="t('settings.dbTables')" />
              <el-table-column align="right" width="140">
                <template #default="{ row }"><span class="pcr-dim pcr-mono">{{ t('settings.dbRows', { n: row.approx_rows ?? 0 }) }}</span></template>
              </el-table-column>
              <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- ── 品牌 / 型号 ───────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'dict'">
      <el-row :gutter="16">
        <el-col :xs="24" :md="10">
          <el-card shadow="never" class="pane-card">
            <template #header>
              {{ t('settings.brands') }}
              <span class="pcr-dim head-count">{{ meta.brands.length }}</span>
            </template>
            <div class="add-row">
              <el-input v-model="newBrand" @keyup.enter="addBrand" />
              <el-button type="primary" :icon="Plus" @click="addBrand" />
            </div>
            <el-table :data="meta.brands" size="small" max-height="420">
              <el-table-column prop="name" :label="t('settings.brandName')" />
              <el-table-column width="60">
                <template #default="{ row }">
                  <el-button size="small" text type="danger" :icon="Delete" @click="removeBrand(row)" />
                </template>
              </el-table-column>
              <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
            </el-table>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="14">
          <el-card shadow="never" class="pane-card">
            <template #header>
              {{ t('settings.models') }}
              <span class="pcr-dim head-count">{{ meta.models.length }}</span>
            </template>
            <div class="add-row">
              <el-input v-model="newModel" @keyup.enter="addModel" />
              <el-button type="primary" :icon="Plus" @click="addModel" />
            </div>
            <el-table :data="meta.models" size="small" max-height="420">
              <el-table-column prop="name" :label="t('settings.modelName')" />
              <el-table-column width="60">
                <template #default="{ row }">
                  <el-button size="small" text type="danger" :icon="Delete" @click="removeModel(row)" />
                </template>
              </el-table-column>
              <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- ── 购买平台 ──────────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'platform'">
      <el-card shadow="never" class="pane-card form-pane">
        <template #header>{{ t('settings.platforms') }}</template>
        <div class="add-row">
          <el-input v-model="newPlatform" maxlength="32" @keyup.enter="addPlatform" />
          <el-button type="primary" :icon="Plus" @click="addPlatform" />
        </div>
        <el-table :data="platformRows" size="small" max-height="420">
          <!-- 显示的是译名，存的是 name：内置的三个在库里是 yahoo / mercari / other -->
          <el-table-column :label="t('settings.platformName')">
            <template #default="{ row }">{{ row.label }}</template>
          </el-table-column>
          <el-table-column width="60">
            <template #default="{ row }">
              <el-button size="small" text type="danger" :icon="Delete" @click="removePlatform(row)" />
            </template>
          </el-table-column>
          <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
        </el-table>
      </el-card>
    </template>

    <!-- ── 账号 ──────────────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'account'">
      <el-row :gutter="16">
        <el-col :xs="24" :md="12">
          <el-card shadow="never" class="pane-card">
            <template #header>{{ t('settings.changePwd') }}</template>
            <el-form ref="pwdFormRef" :model="pwd" :rules="pwdRules" label-width="130px" label-position="left">
              <el-form-item :label="t('settings.oldPwd')" prop="old_password">
                <el-input v-model="pwd.old_password" type="password" show-password />
              </el-form-item>
              <el-form-item :label="t('settings.newPwd')" prop="new_password">
                <el-input v-model="pwd.new_password" type="password" show-password />
              </el-form-item>
              <el-form-item :label="t('settings.confirmPwd')" prop="confirm">
                <el-input v-model="pwd.confirm" type="password" show-password @keyup.enter="changePwd" />
              </el-form-item>
              <div class="form-actions">
                <el-button type="primary" :loading="changingPwd" @click="changePwd">{{ t('settings.changePwd') }}</el-button>
              </div>
            </el-form>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="never" class="pane-card">
            <template #header>{{ t('settings.preferences') }}</template>
            <el-form label-width="130px" label-position="left">
              <el-form-item :label="t('settings.language')">
                <el-select :model-value="locale" @change="setLocale">
                  <el-option v-for="opt in localeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </el-form-item>
            </el-form>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { Coin, Collection, Delete, Picture, Plus, Refresh, Shop, User } from '@element-plus/icons-vue'
import { authApi, optionsApi, systemApi } from '@/api'
import { ElMessage } from '@/utils/notify'
import { currentLocale, localeOptions, setLocale } from '@/i18n'
import { usePlatforms } from '@/composables/usePlatforms'
import { useMetaStore } from '@/stores/meta'
import { useAuthStore } from '@/stores/auth'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const meta = useMetaStore()
const auth = useAuthStore()
const locale = currentLocale

// 二级菜单的定义：顺序即标签条的顺序，name 同时是 URL 上的 ?tab=
const SECTIONS = [
  { name: 'hosting', labelKey: 'settings.tabImageHosting', icon: Picture },
  { name: 'db', labelKey: 'settings.tabDatabase', icon: Coin },
  { name: 'dict', labelKey: 'settings.tabDict', icon: Collection },
  { name: 'platform', labelKey: 'settings.tabPlatform', icon: Shop },
  { name: 'account', labelKey: 'settings.tabAccount', icon: User }
]

// 当前在哪一块记在 URL 上：刷新（或从别处贴链接进来）还停在同一块，
// 改完图床配置刷新页面不会被甩回第一页
const activeTab = ref(SECTIONS.some((s) => s.name === route.query.tab) ? route.query.tab : 'hosting')

// 每块的数据只在第一次点开时拉一次，切回来不重复请求
// 品牌 / 型号 / 平台在 meta.ensure() 里已经一次带回，这里只管另外两块
const loaded = reactive({ hosting: false, db: false })
function ensureSection(name) {
  if (name === 'hosting' && !loaded.hosting) { loaded.hosting = true; loadHosting() }
  if (name === 'db' && !loaded.db) { loaded.db = true; loadDb() }
}
watch(activeTab, (v) => {
  ensureSection(v)
  router.replace({ query: { ...route.query, tab: v } })
})

// ---- 图床 ----
const hosting = reactive({ base_url: '', public_base: '', project: '', token: '', token_set: false, timeout: 30, verify_tls: true })
const savingHosting = ref(false)
const testing = ref(false)
const testResult = ref(null)

async function loadHosting() {
  const cfg = await systemApi.getImageHosting()
  Object.assign(hosting, cfg, { token: '' })
}
async function saveHosting() {
  savingHosting.value = true
  try {
    const payload = { ...hosting }
    delete payload.token_set
    delete payload.configured
    delete payload.media_count
    if (!payload.token) delete payload.token // 空表示不改
    const cfg = await systemApi.saveImageHosting(payload)
    Object.assign(hosting, cfg, { token: '' })
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    savingHosting.value = false
  }
}
async function testHosting() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = { ok: true, ...(await systemApi.testImageHosting()) }
  } catch (e) {
    testResult.value = { ok: false, message: e?.response?.data?.detail || t('settings.testFail') }
  } finally {
    testing.value = false
  }
}
function prettySize(bytes) {
  if (!bytes) return '—'
  const mb = bytes / 1024 / 1024
  return mb >= 1 ? mb.toFixed(0) + ' MB' : (bytes / 1024).toFixed(0) + ' KB'
}

// ---- 数据库 ----
const db = reactive({ conf_path: '', host: '', port: '', database: '', user: '', ok: false, version: '', error: '', tables: [] })
const reconnecting = ref(false)

async function loadDb() {
  try {
    Object.assign(db, await systemApi.databaseStatus())
  } catch { /* 非管理员会 403，忽略 */ }
}
async function reconnect() {
  reconnecting.value = true
  try {
    await systemApi.databaseReconnect()
    ElMessage.success(t('settings.dbConnected'))
    await loadDb()
  } catch { /* 拦截器已提示 */ } finally {
    reconnecting.value = false
  }
}

// ---- 购买平台 ----
// 内置的 yahoo / mercari / other 在库里存的是 key，表里要显示译名，所以过一遍 platformLabel
const newPlatform = ref('')
const { platformLabel } = usePlatforms()
const platformRows = computed(() =>
  meta.platforms.map((p) => ({ ...p, label: platformLabel(p.name) }))
)

async function addPlatform() {
  const name = newPlatform.value.trim()
  if (!name) return
  await optionsApi.createPlatform({ name })
  newPlatform.value = ''
  await meta.reloadPlatforms()
}
async function removePlatform(p) {
  await optionsApi.removePlatform(p.id)
  await meta.reloadPlatforms()
}

// ---- 品牌 / 型号（两者相互独立）----
const newBrand = ref('')
const newModel = ref('')

async function addBrand() {
  const name = newBrand.value.trim()
  if (!name) return
  await optionsApi.createBrand({ name })
  newBrand.value = ''
  await meta.reloadBrands()
}
async function removeBrand(b) {
  await optionsApi.removeBrand(b.id)
  await meta.reloadBrands()
}
async function addModel() {
  const name = newModel.value.trim()
  if (!name) return
  await optionsApi.createModel({ name })
  newModel.value = ''
  await meta.reloadModels()
}
async function removeModel(row) {
  await optionsApi.removeModel(row.id)
  await meta.reloadModels()
}

// ---- 改密码 ----
const pwdFormRef = ref()
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const changingPwd = ref(false)
const pwdRules = {
  old_password: [{ required: true, trigger: 'blur', message: ' ' }],
  new_password: [{ required: true, min: 8, trigger: 'blur', message: t('settings.pwdRule') }],
  confirm: [{
    validator: (_r, v, cb) => (v === pwd.new_password ? cb() : cb(new Error(t('settings.pwdMismatch')))),
    trigger: 'blur'
  }]
}
async function changePwd() {
  await pwdFormRef.value?.validate(async (valid) => {
    if (!valid) return
    changingPwd.value = true
    try {
      await authApi.changePassword({ old_password: pwd.old_password, new_password: pwd.new_password })
      ElMessage.success(t('settings.pwdChanged'))
      setTimeout(() => auth.logout(), 1200)
    } catch { /* 拦截器已提示 */ } finally {
      changingPwd.value = false
    }
  })
}

onMounted(async () => {
  ensureSection(activeTab.value)
  await meta.ensure()   // 品牌与平台清单全站共用，进页面就先备好
})
</script>

<style scoped>
.page-title { font-size: 20px; margin-bottom: 16px; }

/* el-tabs 只当二级标签条用，内容由下面自己渲染 */
.tabs-row { margin-bottom: 18px; }
.settings-tabs :deep(.el-tabs__content) { display: none; }
.settings-tabs :deep(.el-tabs__header) { margin-bottom: 0; }
.settings-tabs :deep(.el-tabs__nav-wrap::after) { background-color: var(--pcr-border); }
.tab-label { display: inline-flex; align-items: center; gap: 6px; }

.pane-card { margin-bottom: 16px; }
/* 单栏的那两块（图床表单、平台清单）不铺满整屏——一行拉到 1900px 宽读起来很累 */
.form-pane { max-width: 760px; }
.full { width: 100% !important; }
.form-actions { margin-top: 12px; }
.mt { margin-top: 12px; }
.kv { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 8px 0; border-bottom: 1px solid #1c2740; font-size: 14px; }
.kv span { color: #8a94a6; white-space: nowrap; }
.kv b { color: #e6edf7; font-weight: 500; word-break: break-all; text-align: right; }
.add-row { display: flex; gap: 8px; margin-bottom: 14px; }
.head-count { font-size: 12px; font-weight: 400; margin-left: 6px; }
.head-tag { margin-left: 8px; }

@media (max-width: 768px) {
  /* 「键 —— 值」两边拉开，靠的是值那侧有富余宽度。数据库这几行的值恰恰是最长的那种
     （conf.ini 全路径、MySQL 版本号），窄屏上左边的键被 white-space: nowrap 顶着不让，
     值只能一路 break-all 折成好几行，读起来像一段乱码。改成上下排。 */
  .kv { flex-direction: column; align-items: flex-start; gap: 2px; }
  .kv b { text-align: left; }
  /* 表单里的 label-width 已由 App.vue 的窄屏规则统一改成标签在上，这里只收一下
     max-width：760px 的限制在手机上本来就不起作用，但按钮行还是该占满 */
  .form-actions { display: flex; gap: 8px; }
  .form-actions .el-button { flex: 1 1 0; margin-left: 0; }
}
</style>
