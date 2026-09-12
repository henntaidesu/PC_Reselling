import { defineStore } from 'pinia'
import { ref } from 'vue'
import { optionsApi } from '@/api'

// 枚举、品牌、型号这类基础字典全站共用一份，避免每个页面各自拉一遍。
export const useMetaStore = defineStore('meta', () => {
  const enums = ref({ statuses: [], media_categories: [], source_platforms: [], currencies: [] })
  const brands = ref([])
  // 型号字典不分品牌，全站一份：显卡详情页的「型号」下拉和整机部件里显卡那一行
  // 用的是同一份候选，各自拉一遍只会拉出两份不同步的清单
  const models = ref([])
  const loaded = ref(false)

  async function ensure() {
    if (loaded.value) return
    await reload()
  }

  async function reload() {
    const [e, b, m] = await Promise.all([optionsApi.enums(), optionsApi.brands(), optionsApi.models()])
    enums.value = e
    brands.value = b.items || []
    models.value = m.items || []
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

  return { enums, brands, models, loaded, ensure, reload, reloadBrands, reloadModels }
})
