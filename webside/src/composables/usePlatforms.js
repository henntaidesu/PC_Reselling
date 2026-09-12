import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMetaStore } from '@/stores/meta'

// 购买平台的下拉选项与显示名。
//
// 平台从后端枚举改成了字典表（系统配置里可增删），但内置的 yahoo / mercari / other
// 三个仍然有中日英三套文案，库里存的也正是这三个 key。所以显示时先看 i18n 里有没有
// 对应的条目，没有才把字典里的名字原样显示——用户自己加的「駿河屋」翻不出来，
// 但也绝不该显示成「platform.駿河屋」。
//
// 选项和显示名必须出自同一处：分头写的话，某天字典里加了一个平台，下拉里有、
// 列表页的那一列却还是原始 key。
export function usePlatforms() {
  const { t, te } = useI18n()
  const meta = useMetaStore()

  function platformLabel(value) {
    if (!value) return ''
    const key = 'platform.' + value
    return te(key) ? t(key) : value
  }

  const platforms = computed(() =>
    meta.platforms.map((p) => ({ value: p.name, label: platformLabel(p.name) }))
  )

  return { platforms, platformLabel }
}
