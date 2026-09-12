// 金额、状态、颜色的展示辅助。所有文案走 i18n，这里只管数值格式和颜色。

// 状态对应的 Element tag 主题色。测试不通过用 danger，成交类用 success，
// 中间流转用 info/warning，让列表扫一眼就能分出「出问题的」和「快到手的」。
// 只有「已打款」（生意最终完成）用绿色；其余状态一律不用绿色。
export const STATUS_TAG_TYPE = {
  purchased: 'info',
  pending_test: 'warning',
  test_passed: 'primary',
  test_failed: 'danger',
  returning: 'primary',
  returned: 'primary',
  forwarding: 'warning',
  received: 'warning',
  paid: 'success'
}

// 状态在流程里的先后，用于按流程排序而不是字母序
export const STATUS_ORDER = [
  'purchased', 'pending_test', 'test_passed', 'test_failed',
  'returning', 'returned', 'forwarding', 'received', 'paid'
]

export function currencySymbol(code) {
  return code === 'JPY' ? '¥' : '￥'
}

// 金额格式化：日元不留小数（日元没有分），人民币两位小数。
export function formatMoney(amount, currency = 'CNY') {
  if (amount === null || amount === undefined || amount === '') return '—'
  const num = Number(amount)
  if (Number.isNaN(num)) return '—'
  const digits = currency === 'JPY' ? 0 : 2
  const symbol = currencySymbol(currency)
  return symbol + num.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

// 人民币专用，概览页大量用
export function cny(amount) {
  return formatMoney(amount, 'CNY')
}

// 汇率的计价单位：多少人民币兑 RATE_UNIT 日元（约 4.32），与银行牌价的写法一致。
// 后端 backend/src/fx/service.py 里也有一个 RATE_UNIT，两边必须一样；日元金额折人民币
// 一律是 × rate ÷ RATE_UNIT。
export const RATE_UNIT = 100

export function formatRate(rate) {
  if (rate === null || rate === undefined) return '—'
  return Number(rate).toFixed(4)
}

// 反向口径（1 人民币 = 多少日元），只拿来给人做常识校验：4.3169 对不对不好说，
// 23.16 一眼就知道。永远不参与计算。
export function inverseRate(rate) {
  const num = Number(rate)
  if (!num || Number.isNaN(num)) return null
  return (RATE_UNIT / num).toFixed(4)
}

// 利润着色：正绿负红，0 和缺失用默认色
export function profitClass(value) {
  if (value === null || value === undefined) return ''
  if (value > 0) return 'pcr-profit'
  if (value < 0) return 'pcr-loss'
  return ''
}

export function firstImage(media) {
  if (!Array.isArray(media)) return null
  return media.find((m) => m.kind === 'image') || media[0] || null
}
