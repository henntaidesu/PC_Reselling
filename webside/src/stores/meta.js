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
  // 归属人 / 出资人：就是用户系统里的账号，[{ id, name, username, is_active }]。
  // 货和钱上存的是 id，页面显示的名字从这里查；停用的人也在里面——历史货上的归属人
  // 要靠它显示名字，只是下拉里不再列出（见 OwnerSelect）。加人、改名在「系统配置 → 用户」
  const people = ref([])
  const loaded = ref(false)

  async function ensure() {
    if (loaded.value) return
    await reload()
  }

  async function reload() {
    const [e, b, m, p, u] = await Promise.all([
      optionsApi.enums(), optionsApi.brands(), optionsApi.models(), optionsApi.platforms(),
      optionsApi.people()
    ])
    enums.value = e
    brands.value = b.items || []
    models.value = m.items || []
    platforms.value = p.items || []
    people.value = u.items || []
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

  // 用户管理里加人、改名、停用之后调它，各处下拉和显示的名字才跟着变
  async function reloadPeople() {
    const u = await optionsApi.people()
    people.value = u.items || []
  }

  // id → 显示名。查询串里带回来的是字符串，按数字比；查不到（刚被删、还没刷新）就原样显示
  function personName(id) {
    if (id === null || id === undefined || id === '') return ''
    const hit = people.value.find((x) => x.id === Number(id))
    return hit ? hit.name : String(id)
  }

  return {
    enums, brands, models, platforms, people, loaded,
    ensure, reload, reloadBrands, reloadModels, reloadPlatforms, reloadPeople, personName
  }
})
