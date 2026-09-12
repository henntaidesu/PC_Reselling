// 金额、状态、颜色的展示辅助。所有文案走 i18n，这里只管数值格式和颜色。

// 状态色：一个状态一个固定颜色，列表里的标签、概览页的图共用这一份，改色只改这里。
// 不用 el-tag 的 type：type 只有五种，状态有十个，用 type 会把「回国中 / 转寄中 / 已签收」
// 挤成同一个颜色，而这几步之间的区别恰恰是最需要一眼看出来的。
//
// 取值的三条规则，加状态时照着挑：
//   1. 红与绿是语义色，只有「测试不通过」和「已打款」能用——列表里扫一眼就分得出
//      「出事的」和「钱到手的」，别的状态染了绿就没这个效果了。
//   2. 「等人动手」的用暖色（待测试琥珀 / 转寄中橙），「只是在路上」的用冷色
//      （测试通过蓝 / 回国中紫 / 已回国粉 / 已签收青）。
//   3. 「意向购入」东西还不是自己的，用中性灰，并且标签画成描边（见 StatusTag.vue），
//      跟所有「已经花了钱」的状态在视觉上隔开。
export const STATUS_COLOR = {
  intent: '#8892a4',
  purchased: '#5a6a88',
  pending_test: '#c98500',
  test_passed: '#3987e5',
  test_failed: '#d03b3b',
  returning: '#7c5cff',
  returned: '#d55181',
  forwarding: '#d95926',
  received: '#0e94a8',
  paid: '#008300'
}

// 画成描边而不是实心的状态：东西还没买下来，不该和已经花了钱的那些长得一样重。
export const STATUS_OUTLINED = new Set(['intent'])

export function statusColor(status) {
  return STATUS_COLOR[status] || STATUS_COLOR.purchased
}

// 状态在流程里的先后，用于按流程排序而不是字母序
export const STATUS_ORDER = [
  'intent', 'purchased', 'pending_test', 'test_passed', 'test_failed',
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

// 日元专用。列表里成本会人民币、日元各显示一次——货是在日本买的，对着日站的
// 成交价复核时看日元才顺手
export function jpy(amount) {
  return formatMoney(amount, 'JPY')
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
