import { defineStore } from 'pinia'
import { ref } from 'vue'
import { optionsApi } from '@/api'

// 枚举、品牌、型号、购买平台这类基础字典全站共用一份，避免每个页面各自拉一遍。
export const useMetaStore = defineStore('meta', () => {
  const enums = ref({ statuses: [], media_categories: [], device_part_types: [], currencies: [] })
  const brands = ref([])
  // 购买平台以前是后端写死的枚举，现在是用户自己维护的字典表（系统配置里可增删）
  const platforms = ref([])
  // 型号字典不分品牌，全站一份：显卡详情页的「型号」下拉和整机部件里显卡那一行
  // 用的是同一份候选，各自拉一遍只会拉出两份不同步的清单
  const models = ref([])
  // 出资人：资金池的注资和显卡 / 整机的出资比例共用这一份候选清单。
  // 只读——新名字是在用到的地方现敲的，由后端顺手落进字典（funds.ensure_contributor）
  const contributors = ref([])
  const loaded = ref(false)

  async function ensure() {
    if (loaded.value) return
    await reload()
  }

  async function reload() {
    const [e, b, m, p, c] = await Promise.all([
      optionsApi.enums(), optionsApi.brands(), optionsApi.models(), optionsApi.platforms(),
      optionsApi.fundContributors()
    ])
    enums.value = e
    brands.value = b.items || []
    models.value = m.items || []
    platforms.value = p.items || []
    contributors.value = (c.items || []).map((x) => x.name)
    loaded.value = true
  }

  async function reloadBrands() {
    const b = await optionsApi.brands()
    brands.value = b.items || []
  }

  async function reloadModels() {
    const m = await optionsApi.models()
    models.value = m.items || []
  }

  async function reloadPlatforms() {
    const p = await optionsApi.platforms()
    platforms.value = p.items || []
  }

  // 详情页里现敲了一个新出资人之后调它：不刷新的话，那个名字在同一次会话里
  // 换一张卡就又不在候选里了
  async function reloadContributors() {
    const c = await optionsApi.fundContributors()
    contributors.value = (c.items || []).map((x) => x.name)
  }

  return {
    enums, brands, models, platforms, contributors, loaded,
    ensure, reload, reloadBrands, reloadModels, reloadPlatforms, reloadContributors
  }
})
