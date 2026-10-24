<template>
  <div class="login-page">
    <el-card class="login-card" shadow="hover">
      <template #header>
        <div class="title-wrap">
          <div class="title-wrap__left">
            <el-icon size="26"><UserFilled /></el-icon>
            <span>{{ t('login.title') }}</span>
          </div>
          <el-select
            :model-value="locale"
            size="small"
            class="login-lang-switcher"
            @change="onLocaleChange"
          >
            <el-option
              v-for="opt in localeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
      </template>

      <!-- 关闭浏览器账号密码自动填充：密码框用 new-password（Chrome 忽略 off 但认它）。
           用户名框关掉 iOS 的自动首字母大写与纠错：不关的话在 iPhone 上敲 admin 会变成
           Admin，登录失败，而输入框里那个大写 A 很难被注意到。 -->
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        autocomplete="off"
        @submit.prevent="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            :placeholder="t('login.placeholderUser')"
            size="large"
            clearable
            autocomplete="off"
            autocapitalize="off"
            autocorrect="off"
            spellcheck="false"
            enterkeyhint="next"
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            :placeholder="t('login.placeholderPwd')"
            size="large"
            show-password
            autocomplete="new-password"
            enterkeyhint="go"
          />
        </el-form-item>
        <el-form-item>
          <el-button native-type="submit" type="primary" size="large" :loading="loading" style="width: 100%">
            {{ t('login.submit') }}
          </el-button>
        </el-form-item>
      </el-form>

      <!-- 门户单点登录：系统配置 → 单点登录 里开启后才出现（/sso/status） -->
      <template v-if="ssoEnabled">
        <el-divider>{{ t('login.or') }}</el-divider>
        <el-button size="large" class="sso-btn" :loading="ssoLoading" @click="handleSsoLogin">
          {{ ssoLabel || t('login.sso') }}
        </el-button>
      </template>

      <div class="tip">{{ t('login.defaultAccount') }}</div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { currentLocale, localeOptions, setLocale } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { ssoApi } from '@/api'
import { ElMessage } from '@/utils/notify'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const locale = currentLocale
const loading = ref(false)
const formRef = ref()
const form = reactive({ username: '', password: '' })

const rules = computed(() => ({
  username: [{ required: true, message: t('login.placeholderUser'), trigger: 'blur' }],
  password: [{ required: true, message: t('login.placeholderPwd'), trigger: 'blur' }]
}))

function onLocaleChange(val) {
  setLocale(val)
}

// 正常用 router 跳；个别情况下（并发导航/守卫）router.replace 会静默失败，
// 兜底直接改 hash 强制跳转，保证登录后一定离开登录页。
async function goHome() {
  try {
    await router.replace('/dashboard')
  } catch {
    window.location.hash = '#/dashboard'
  }
}

async function handleLogin() {
  // 校验不过时 validate() 会 reject——单独 try 住，不让它把后面的登录流程也带崩
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    await goHome()
  } finally {
    loading.value = false
  }
}

// ---- 门户单点登录 ----
const ssoEnabled = ref(false)
const ssoLabel = ref('')
const ssoLoading = ref(false)

function handleSsoLogin() {
  ssoLoading.value = true
  location.href = ssoApi.loginUrl()   // 整页跳转，门户走完会带着一次性票跳回本页
}

onMounted(async () => {
  const { sso_ticket: ticket, sso_error: failed } = route.query
  if (ticket || failed) router.replace({ path: '/login' })   // 票只能用一次，别留在地址栏
  if (failed) ElMessage.error(t('login.ssoFailed') + failed)
  if (ticket) {
    ssoLoading.value = true
    try {
      auth.enter(await ssoApi.exchange(String(ticket)))
      await goHome()
      return
    } catch {
      /* http.js 已提示错误，留在登录页 */
    } finally {
      ssoLoading.value = false
    }
  }
  try {
    const st = await ssoApi.status()
    ssoEnabled.value = Boolean(st.enabled)
    ssoLabel.value = st.label || ''
  } catch {
    ssoEnabled.value = false
  }
})
</script>

<style scoped>
.login-page {
  min-height: calc(100 * var(--app-vh));
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(circle at top, #1f2a44 0%, #0b1220 55%);
  padding: 16px;
  position: relative;
}

.login-card {
  width: 100%;
  max-width: 520px;
  border: 1px solid #2a3446;
}

.title-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
  color: #b8c4d0;
}

.title-wrap__left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
}

.login-lang-switcher {
  width: 130px;
  flex-shrink: 0;
}

/* 覆盖 App.vue 中 .el-input { width: 180px } 的全局规则 */
.login-card :deep(.el-form .el-input) {
  width: 100% !important;
}

.sso-btn { width: 100%; margin-bottom: 18px; }
.login-card :deep(.el-divider__text) { background: var(--el-card-bg-color, var(--el-bg-color)); color: #94a3b8; }

.tip {
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
}

@media (max-width: 768px) {
  .login-page {
    padding: max(16px, env(safe-area-inset-top, 0px))
             max(16px, env(safe-area-inset-right, 0px))
             max(16px, env(safe-area-inset-bottom, 0px))
             max(16px, env(safe-area-inset-left, 0px));
  }
  .login-lang-switcher {
    width: 110px !important;
    min-width: 0;
  }
  .title-wrap { gap: 8px; font-size: 16px; }
  .title-wrap__left {
    flex: 1 1 auto;
    overflow: hidden;
    text-overflow: ellipsis;
  }
}
</style>
