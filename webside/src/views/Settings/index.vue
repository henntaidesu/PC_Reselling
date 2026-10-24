<template>
  <div class="settings-page">
    <h2 class="page-title">{{ t('settings.title') }}</h2>

    <!-- 二级菜单：el-tabs 只当标签条用，内容在下面按 activeTab 自己渲染。
         挂进 el-tab-pane 的话五块会一次性全挂载，图床配置与数据库状态（含整库表清单）
         每次进页面都要白拉一遍——配 ensureSection 的按需加载，把这两发请求推迟到真点开 -->
    <div class="tabs-row">
      <el-tabs v-model="activeTab" class="settings-tabs pcr-touch-tabs">
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
            <el-input v-model="hosting.base_url" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-form-item :label="t('settings.publicBase')">
            <el-input v-model="hosting.public_base" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-form-item :label="t('settings.project')">
            <el-input v-model="hosting.project" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-form-item :label="t('settings.token')">
            <el-input v-model="hosting.token" type="password" show-password autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-row :gutter="16">
            <el-col :xs="24" :sm="12">
              <el-form-item :label="t('settings.timeout')">
                <el-input-number v-model="hosting.timeout" :min="5" :max="600" :controls="false" inputmode="numeric" class="full" />
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

    <!-- ── 用户（管理员）──────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'users'">
      <el-card shadow="never" class="pane-card">
        <template #header>
          <div class="head-row">
            <span>{{ t('users.title') }}<span class="pcr-dim head-count">{{ users.length }}</span></span>
            <el-button type="primary" size="small" :icon="Plus" @click="openUserDialog()">{{ t('users.add') }}</el-button>
          </div>
        </template>

        <!-- 宽表在紧凑宽度换卡片列表：同一批数据、同一组处理函数，不是第二套列表 -->
        <div v-if="isCompact" v-loading="usersLoading" class="user-cards">
          <div v-for="u in users" :key="u.id" class="user-card" :class="{ 'is-off': !u.is_active }">
            <div class="user-card__head">
              <b>{{ u.display_name }}</b>
              <span class="pcr-dim pcr-mono">{{ u.username }}</span>
              <el-tag v-if="u.is_admin" size="small" type="warning" effect="plain">{{ t('users.admin') }}</el-tag>
              <el-tag v-if="!u.is_active" size="small" type="info">{{ t('users.disabled') }}</el-tag>
            </div>
            <div class="user-card__meta">
              <el-tag v-if="u.has_password" size="small" effect="plain">{{ t('users.viaPassword') }}</el-tag>
              <el-tag v-if="u.portal_username !== null" size="small" type="success" effect="plain">
                {{ t('users.viaPortal') }} · {{ u.portal_username }}
              </el-tag>
              <span class="pcr-dim">{{ t('users.lastActive') }} {{ u.last_active_at || '—' }}</span>
            </div>
            <div class="user-card__ops">
              <el-button size="small" @click="openUserDialog(u)">{{ t('common.edit') }}</el-button>
              <el-button size="small" :disabled="u.id === auth.user?.id" @click="patchUser(u, { is_active: !u.is_active })">
                {{ u.is_active ? t('users.disable') : t('users.enable') }}
              </el-button>
              <el-button size="small" @click="resetUserPwd(u)">{{ t('users.resetPwd') }}</el-button>
              <el-button size="small" @click="revokeUser(u)">{{ t('users.revoke') }}</el-button>
              <el-button size="small" type="danger" plain :disabled="u.id === auth.user?.id" @click="removeUser(u)">{{ t('common.delete') }}</el-button>
            </div>
          </div>
        </div>
        <el-table v-else v-loading="usersLoading" :data="users" size="small">
          <el-table-column :label="t('users.username')" min-width="150">
            <template #default="{ row }">
              <span class="pcr-mono">{{ row.username }}</span>
              <el-tag v-if="row.is_admin" size="small" type="warning" effect="plain" class="ml">{{ t('users.admin') }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="display_name" :label="t('users.displayName')" min-width="120" />
          <el-table-column :label="t('users.loginMethods')" min-width="200">
            <template #default="{ row }">
              <el-tag v-if="row.has_password" size="small" effect="plain">{{ t('users.viaPassword') }}</el-tag>
              <el-tag v-if="row.portal_username !== null" size="small" type="success" effect="plain" class="ml">
                {{ t('users.viaPortal') }} · {{ row.portal_username }}
              </el-tag>
              <span v-if="!row.has_password && row.portal_username === null" class="pcr-dim">{{ t('users.noMethod') }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="t('users.active')" width="80" align="center">
            <template #default="{ row }">
              <el-switch :model-value="row.is_active" size="small" :disabled="row.id === auth.user?.id"
                         @change="(v) => patchUser(row, { is_active: v })" />
            </template>
          </el-table-column>
          <el-table-column :label="t('users.lastActive')" width="160">
            <template #default="{ row }"><span class="pcr-dim pcr-mono">{{ row.last_active_at || '—' }}</span></template>
          </el-table-column>
          <el-table-column width="300" align="right">
            <template #default="{ row }">
              <el-button size="small" text @click="openUserDialog(row)">{{ t('common.edit') }}</el-button>
              <el-button size="small" text @click="resetUserPwd(row)">{{ t('users.resetPwd') }}</el-button>
              <el-button size="small" text @click="revokeUser(row)">{{ t('users.revoke') }}</el-button>
              <el-button size="small" text type="danger" :disabled="row.id === auth.user?.id" @click="removeUser(row)">{{ t('common.delete') }}</el-button>
            </template>
          </el-table-column>
          <template #empty><span class="pcr-dim">{{ t('common.noData') }}</span></template>
        </el-table>
      </el-card>

      <el-dialog v-model="userDialog" :title="userForm.id ? t('users.edit') : t('users.add')" width="460px" align-center>
        <el-form :model="userForm" label-width="110px" label-position="left">
          <el-form-item :label="t('users.username')" required>
            <el-input v-model="userForm.username" maxlength="64" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-form-item :label="t('users.displayName')">
            <el-input v-model="userForm.display_name" maxlength="64" />
          </el-form-item>
          <el-form-item v-if="!userForm.id" :label="t('users.password')">
            <el-input v-model="userForm.password" type="password" show-password autocomplete="new-password"
                      :placeholder="t('users.passwordOptional')" />
          </el-form-item>
          <el-form-item :label="t('users.admin')">
            <el-switch v-model="userForm.is_admin" :disabled="userForm.id === auth.user?.id" />
          </el-form-item>
        </el-form>
        <div v-if="!userForm.id" class="pcr-dim hint">{{ t('users.createHint') }}</div>
        <template #footer>
          <el-button @click="userDialog = false">{{ t('common.cancel') }}</el-button>
          <el-button type="primary" :loading="userSaving" @click="submitUser">{{ t('common.save') }}</el-button>
        </template>
      </el-dialog>
    </template>

    <!-- ── 门户单点登录（管理员）──────────────────────────────────────── -->
    <template v-else-if="activeTab === 'sso'">
      <el-card shadow="never" class="pane-card form-pane">
        <template #header>
          {{ t('sso.title') }}
          <el-tag :type="sso.active ? 'success' : 'info'" effect="dark" size="small" class="head-tag">
            {{ sso.active ? t('sso.on') : t('sso.off') }}
          </el-tag>
        </template>
        <el-form label-width="150px" label-position="left">
          <el-form-item :label="t('sso.enable')">
            <el-switch :model-value="sso.enabled" :loading="ssoSwitching" :disabled="!sso.configured"
                       :before-change="toggleSso" />
            <span v-if="!sso.configured" class="pcr-dim ml">{{ t('sso.needConfig') }}</span>
          </el-form-item>
          <el-form-item :label="t('sso.portalUrl')">
            <el-input v-model="ssoForm.portal_url" placeholder="https://portal.example.com" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-form-item :label="t('sso.internalUrl')">
            <el-input v-model="ssoForm.internal_url" :placeholder="t('sso.internalUrlPlaceholder')" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-form-item label="Client ID">
            <el-input v-model="ssoForm.client_id" autocapitalize="off" autocorrect="off" spellcheck="false" />
          </el-form-item>
          <el-form-item label="Client Secret">
            <el-input v-model="ssoForm.client_secret" type="password" show-password autocomplete="new-password"
                      autocapitalize="off" autocorrect="off" spellcheck="false"
                      :placeholder="sso.secret_set ? t('sso.secretKeep') : ''" />
          </el-form-item>
          <el-form-item :label="t('sso.autoCreate')">
            <el-switch v-model="ssoForm.auto_create" />
          </el-form-item>
          <el-form-item :label="t('sso.buttonLabel')">
            <el-input v-model="ssoForm.button_label" maxlength="20" :placeholder="t('login.sso')" />
          </el-form-item>
          <div class="form-actions">
            <el-button type="primary" :loading="ssoSaving" @click="saveSso">{{ t('common.save') }}</el-button>
            <el-button :loading="ssoTesting" :disabled="!sso.configured" @click="testSso">{{ t('settings.test') }}</el-button>
          </div>
          <el-alert v-if="ssoTestResult" :type="ssoTestResult.ok ? 'success' : 'error'" :closable="false" show-icon class="mt">
            {{ ssoTestResult.message }}
          </el-alert>
        </el-form>

        <!-- 门户卡片上要登记的地址按当前页面拼：经门户代理打开时拼出来的就是代理后的那个 -->
        <div class="sso-hint">
          <div>{{ t('sso.callbackHint') }}</div>
          <code class="pcr-mono">{{ ssoCallbackUrl }}</code>
          <div>{{ t('sso.loginHint') }}</div>
          <code class="pcr-mono">{{ ssoLoginUrl }}</code>
          <div class="pcr-dim">{{ isProxied ? t('sso.proxiedHint') : t('sso.directHint') }}</div>
        </div>
      </el-card>

      <el-card shadow="never" class="pane-card form-pane">
        <template #header>{{ t('sso.bindings') }}<span class="pcr-dim head-count">{{ ssoBindings.length }}</span></template>
        <el-table :data="ssoBindings" v-loading="ssoBindingsLoading" size="small">
          <el-table-column :label="t('sso.portalUser')" min-width="140">
            <template #default="{ row }">{{ row.portal_username }} <span class="pcr-dim">#{{ row.portal_sub }}</span></template>
          </el-table-column>
          <el-table-column :label="t('sso.localUser')" min-width="120">
            <template #default="{ row }"><span class="pcr-mono">{{ row.username }}</span></template>
          </el-table-column>
          <el-table-column v-if="!isMobile" prop="last_login_at" :label="t('sso.lastLogin')" width="160" />
          <el-table-column width="70" align="right">
            <template #default="{ row }">
              <el-button link type="danger" size="small" @click="unbindSso(row)">{{ t('sso.unbind') }}</el-button>
            </template>
          </el-table-column>
          <template #empty><span class="pcr-dim">{{ t('sso.noBindings') }}</span></template>
        </el-table>
      </el-card>
    </template>

    <!-- ── 账号 ──────────────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'account'">
      <el-row :gutter="16">
        <el-col :xs="24" :md="12">
          <el-card shadow="never" class="pane-card">
            <template #header>{{ auth.user?.has_password === false ? t('settings.setPwd') : t('settings.changePwd') }}</template>
            <div v-if="auth.user?.has_password === false" class="pcr-dim hint">{{ t('settings.noPwdHint') }}</div>
            <el-form ref="pwdFormRef" :model="pwd" :rules="pwdRules" label-width="130px" label-position="left">
              <el-form-item :label="t('settings.newPwd')" prop="new_password">
                <el-input v-model="pwd.new_password" type="password" show-password autocomplete="new-password" />
              </el-form-item>
              <el-form-item :label="t('settings.confirmPwd')" prop="confirm">
                <el-input v-model="pwd.confirm" type="password" show-password autocomplete="new-password" @keyup.enter="changePwd" />
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
              <el-form-item :label="t('users.username')">
                <span class="pcr-mono">{{ auth.user?.username }}</span>
              </el-form-item>
              <el-form-item :label="t('users.displayName')">
                <div class="add-row no-mb">
                  <el-input v-model="profileName" maxlength="64" @keyup.enter="saveProfile" />
                  <el-button :loading="profileSaving" @click="saveProfile">{{ t('common.save') }}</el-button>
                </div>
              </el-form-item>
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
import { ElMessageBox } from 'element-plus'
import { Coin, Collection, Connection, Delete, Picture, Plus, Refresh, Shop, User, UserFilled } from '@element-plus/icons-vue'
import { authApi, optionsApi, ssoApi, systemApi, usersApi } from '@/api'
import { useIsCompact, useIsMobile } from '@/composables/useIsMobile'
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

const { isCompact } = useIsCompact()
const { isMobile } = useIsMobile()

// 二级菜单的定义：顺序即标签条的顺序，name 同时是 URL 上的 ?tab=。
// adminOnly 的几块后端整条挂着 require_admin，普通用户点进去也只会收到 403，干脆不给标签
const ALL_SECTIONS = [
  { name: 'hosting', labelKey: 'settings.tabImageHosting', icon: Picture },
  { name: 'db', labelKey: 'settings.tabDatabase', icon: Coin, adminOnly: true },
  { name: 'dict', labelKey: 'settings.tabDict', icon: Collection },
  { name: 'platform', labelKey: 'settings.tabPlatform', icon: Shop },
  { name: 'users', labelKey: 'settings.tabUsers', icon: UserFilled, adminOnly: true },
  { name: 'sso', labelKey: 'settings.tabSso', icon: Connection, adminOnly: true },
  { name: 'account', labelKey: 'settings.tabAccount', icon: User }
]
const SECTIONS = computed(() => ALL_SECTIONS.filter((s) => !s.adminOnly || auth.isAdmin))

// 当前在哪一块记在 URL 上：刷新（或从别处贴链接进来）还停在同一块，
// 改完图床配置刷新页面不会被甩回第一页
const activeTab = ref(SECTIONS.value.some((s) => s.name === route.query.tab) ? route.query.tab : 'hosting')

// 每块的数据只在第一次点开时拉一次，切回来不重复请求
// 品牌 / 型号 / 平台在 meta.ensure() 里已经一次带回，这里只管另外几块
const loaded = reactive({ hosting: false, db: false, users: false, sso: false })
function ensureSection(name) {
  if (name === 'hosting' && !loaded.hosting) { loaded.hosting = true; loadHosting() }
  if (name === 'db' && !loaded.db) { loaded.db = true; loadDb() }
  if (name === 'users' && !loaded.users) { loaded.users = true; loadUsers() }
  if (name === 'sso' && !loaded.sso) { loaded.sso = true; loadSso() }
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

// ---- 用户（管理员）----
const users = ref([])
const usersLoading = ref(false)
const userDialog = ref(false)
const userSaving = ref(false)
const userForm = reactive({ id: null, username: '', display_name: '', password: '', is_admin: false })

async function loadUsers() {
  usersLoading.value = true
  try {
    users.value = await usersApi.list()
  } catch { /* 拦截器已提示 */ } finally {
    usersLoading.value = false
  }
}
// 改完一行只替换那一行：后端每个写接口都回这个人的最新形状
function putUser(u) {
  const i = users.value.findIndex((x) => x.id === u.id)
  if (i >= 0) users.value.splice(i, 1, u)
  else users.value.push(u)
  if (u.id === auth.user?.id) auth.refresh()
}
function openUserDialog(row) {
  Object.assign(userForm, {
    id: row?.id ?? null,
    username: row?.username || '',
    // 后端在没填显示名时回的是用户名，编辑框里原样摆出来会让人以为填过
    display_name: row && row.display_name !== row.username ? row.display_name : '',
    password: '',
    is_admin: Boolean(row?.is_admin)
  })
  userDialog.value = true
}
async function submitUser() {
  const username = userForm.username.trim()
  if (!username) return ElMessage.warning(t('users.usernameRequired'))
  if (!userForm.id && userForm.password && userForm.password.length < 8) return ElMessage.warning(t('settings.pwdRule'))
  userSaving.value = true
  try {
    const payload = { username, display_name: userForm.display_name.trim(), is_admin: userForm.is_admin }
    if (userForm.id) {
      putUser(await usersApi.update(userForm.id, payload))
    } else {
      if (userForm.password) payload.password = userForm.password
      putUser(await usersApi.create(payload))
    }
    userDialog.value = false
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    userSaving.value = false
  }
}
async function patchUser(row, patch) {
  try {
    putUser(await usersApi.update(row.id, patch))
  } catch { /* 拦截器已提示；开关停在原状，因为 model-value 取的是行上的值 */ }
}
async function resetUserPwd(row) {
  let password
  try {
    ({ value: password } = await ElMessageBox.prompt(t('users.resetPwdPrompt', { name: row.username }), t('users.resetPwd'), {
      inputType: 'password',
      inputValidator: (v) => (Boolean(v) && v.length >= 8) || t('settings.pwdRule')
    }))
  } catch { return }
  try {
    putUser(await usersApi.resetPassword(row.id, password))
    ElMessage.success(t('users.pwdReset'))
    // 重置的是自己的密码：令牌已随 token_version 作废，下一个请求就会 401，直接回登录页
    if (row.id === auth.user?.id) setTimeout(() => auth.logout(), 1200)
  } catch { /* 拦截器已提示 */ }
}
async function revokeUser(row) {
  try {
    await ElMessageBox.confirm(t('users.revokeConfirm', { name: row.username }), t('users.revoke'), { type: 'warning' })
  } catch { return }
  try {
    putUser(await usersApi.revoke(row.id))
    ElMessage.success(t('users.revoked'))
    if (row.id === auth.user?.id) setTimeout(() => auth.logout(), 1200)
  } catch { /* 拦截器已提示 */ }
}
async function removeUser(row) {
  try {
    await ElMessageBox.confirm(t('users.removeConfirm', { name: row.username }), t('common.delete'), { type: 'warning' })
  } catch { return }
  try {
    await usersApi.remove(row.id)
    users.value = users.value.filter((x) => x.id !== row.id)
    ssoBindings.value = ssoBindings.value.filter((b) => b.user_id !== row.id)
  } catch { /* 拦截器已提示 */ }
}

// ---- 门户单点登录（管理员）----
const sso = reactive({ enabled: false, active: false, configured: false, secret_set: false,
  callback_path: 'api/v1/sso/callback', login_path: 'api/v1/sso/login' })
const ssoForm = reactive({ portal_url: '', internal_url: '', client_id: '', client_secret: '', auto_create: true, button_label: '' })
const ssoSaving = ref(false)
const ssoTesting = ref(false)
const ssoSwitching = ref(false)
const ssoTestResult = ref(null)
const ssoBindings = ref([])
const ssoBindingsLoading = ref(false)

// hash 路由下 pathname 就是站点根：直接访问是 /，经门户代理是 /api/proxy/<卡片 id>/，
// 整站模式再多一截 __portal__/http/<上游>/
const siteRoot = location.origin + location.pathname
const isProxied = /^\/api\/proxy\/[^/]+\//.test(location.pathname)
const ssoCallbackUrl = computed(() => siteRoot + sso.callback_path)
const ssoLoginUrl = computed(() => siteRoot + sso.login_path)

function applySso(cfg) {
  Object.assign(sso, cfg)
  Object.assign(ssoForm, {
    portal_url: cfg.portal_url, internal_url: cfg.internal_url, client_id: cfg.client_id,
    client_secret: '', auto_create: cfg.auto_create, button_label: cfg.button_label
  })
}
async function loadSso() {
  try {
    applySso(await ssoApi.getConfig())
  } catch { return }
  loadSsoBindings()
}
async function loadSsoBindings() {
  ssoBindingsLoading.value = true
  try {
    ssoBindings.value = await ssoApi.bindings()
  } catch { /* 拦截器已提示 */ } finally {
    ssoBindingsLoading.value = false
  }
}
async function saveSso() {
  ssoSaving.value = true
  try {
    const payload = { ...ssoForm }
    if (!payload.client_secret) delete payload.client_secret   // 留空 = 不改已保存的 Secret
    applySso(await ssoApi.saveConfig(payload))
    ssoTestResult.value = null
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    ssoSaving.value = false
  }
}
async function testSso() {
  ssoTesting.value = true
  ssoTestResult.value = null
  try {
    ssoTestResult.value = await ssoApi.test()
  } catch (e) {
    ssoTestResult.value = { ok: false, message: e?.response?.data?.detail || t('settings.testFail') }
  } finally {
    ssoTesting.value = false
  }
}
// el-switch 的 before-change：状态按服务端结果写回，返回 false 不让开关自己翻
async function toggleSso() {
  ssoSwitching.value = true
  try {
    applySso(await ssoApi.saveConfig({ enabled: !sso.enabled }))
  } catch { /* 拦截器已提示 */ } finally {
    ssoSwitching.value = false
  }
  return false
}
async function unbindSso(row) {
  try {
    await ElMessageBox.confirm(t('sso.unbindConfirm', { name: row.portal_username }), t('sso.unbind'), { type: 'warning' })
  } catch { return }
  try {
    await ssoApi.unbind(row.id)
    await Promise.all([loadSsoBindings(), loaded.users ? loadUsers() : null])
  } catch { /* 拦截器已提示 */ }
}

// ---- 显示名 ----
const profileName = ref(auth.user && auth.user.display_name !== auth.user.username ? auth.user.display_name || '' : '')
const profileSaving = ref(false)
async function saveProfile() {
  profileSaving.value = true
  try {
    auth.setUser(await authApi.updateProfile({ display_name: profileName.value.trim() }))
    ElMessage.success(t('common.saved'))
  } catch { /* 拦截器已提示 */ } finally {
    profileSaving.value = false
  }
}

// ---- 改密码 ----
const pwdFormRef = ref()
const pwd = reactive({ new_password: '', confirm: '' })
const changingPwd = ref(false)
const pwdRules = {
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
      await authApi.changePassword({ new_password: pwd.new_password })
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
.head-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.ml { margin-left: 6px; }
.hint { font-size: 12px; margin-bottom: 12px; line-height: 1.6; }
.add-row.no-mb { margin-bottom: 0; width: 100%; }
.sso-hint { margin-top: 18px; padding-top: 14px; border-top: 1px solid #1c2740; font-size: 12px; color: #8a94a6; line-height: 1.8; }
.sso-hint code { display: block; margin-bottom: 6px; color: #e6edf7; word-break: break-all; }

/* 用户卡片列表（紧凑宽度）：平板两列、手机一列 */
.user-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; min-height: 60px; }
.user-card { border: 1px solid var(--pcr-border); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.user-card.is-off { opacity: 0.6; }
.user-card__head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.user-card__meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; }
.user-card__ops { display: flex; gap: 6px; flex-wrap: wrap; }
.user-card__ops .el-button { margin-left: 0; }

@media (hover: none) {
  /* 「+」按钮与输入框等高，热区就是整个按钮 */
  .add-row .el-button { min-width: 48px; }
}

@media (max-width: 768px) {
  /* 「键 —— 值」两边拉开，靠的是值那侧有富余宽度。数据库这几行的值恰恰是最长的那种
     （conf.ini 全路径、MySQL 版本号），窄屏上左边的键被 white-space: nowrap 顶着不让，
     值只能一路 break-all 折成好几行，读起来像一段乱码。改成上下排。 */
  .kv { flex-direction: column; align-items: flex-start; gap: 2px; }
  .kv b { text-align: left; }
  .user-cards { grid-template-columns: 1fr; }
  /* 表单里的 label-width 已由 App.vue 的窄屏规则统一改成标签在上，这里只收一下
     max-width：760px 的限制在手机上本来就不起作用，但按钮行还是该占满 */
  .form-actions { display: flex; gap: 8px; }
  .form-actions .el-button { flex: 1 1 0; margin-left: 0; }
}
</style>
