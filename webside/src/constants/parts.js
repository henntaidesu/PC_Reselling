// 部件类型各自的品牌候选。
//
// 为什么要分类型：CPU 的品牌只可能是 Intel / AMD，硬盘和主板则完全是另一批厂商。
// 一个统一的品牌文本框等于每次都靠人自己回忆并手打，几台机器之后同一个厂商就会有
// 三种写法，之后想按品牌归类就全乱了。
//
// 候选值一律用拉丁写法（ASUS、Kingston、Seasonic），三种界面语言下都不用翻译，也和
// 日本站上的原始标注对得上。除 CPU 外都允许现场输入清单外的值（filterable +
// allow-create），清单只是省事的默认项，不是白名单。

// 一台机器必然有的六个部件槽位，顺序即标签页顺序。它们**每类至少留一件**：
// 不用每次点六下「添加」，也删不到零（详情页在只剩一件时不给删除按钮）。
// 空槽位不会落库，摆着不会污染数据。
export const DEFAULT_PART_TYPES = ['cpu', 'gpu', 'ram', 'disk', 'motherboard', 'psu']

// 详情页的部件标签页 = 六个必有槽位 + 一个「其他」。散热 / 机箱这些历史类型没有自己的
// 标签页，统一归到「其他」下面显示——与其为每个小类都挂一个多半是空的标签，不如给个兜底。
export const PART_TABS = [...DEFAULT_PART_TYPES, 'other']

// 这一行归哪个标签页。六个标准类型各归各的，其余一律算「其他」。
export function partTab(partType) {
  return DEFAULT_PART_TYPES.includes(partType) ? partType : 'other'
}

export const PART_SCHEMA = {
  cpu: {
    // 用户明确要求：CPU 品牌只有这两个，所以不允许现场新建
    brands: ['Intel', 'AMD'],
    brandStrict: true
  },
  gpu: {
    // 显卡的品牌与型号走系统里已有的字典（系统配置 → 品牌/型号），下面这份只是字典为空时的兜底
    brands: ['ASUS', 'MSI', 'GIGABYTE', 'ZOTAC', 'PALIT', 'INNO3D', 'COLORFUL', 'GALAX', 'NVIDIA'],
    brandStrict: false
  },
  ram: {
    brands: ['Kingston', 'Corsair', 'G.SKILL', 'Crucial', 'ADATA', 'Samsung', 'SK hynix', 'Micron', 'TEAM'],
    brandStrict: false
  },
  disk: {
    brands: ['Samsung', 'Western Digital', 'Seagate', 'KIOXIA', 'Crucial', 'SanDisk', 'Intel', 'ADATA'],
    brandStrict: false
  },
  motherboard: {
    brands: ['ASUS', 'MSI', 'GIGABYTE', 'ASRock', 'BIOSTAR', 'COLORFUL'],
    brandStrict: false
  },
  psu: {
    brands: ['Seasonic', 'Corsair', 'Super Flower', 'Cooler Master', 'Antec', 'EVGA', 'be quiet!', 'Great Wall'],
    brandStrict: false
  },
  cooler: {
    brands: ['Thermalright', 'Noctua', 'DeepCool', 'Cooler Master', 'Corsair', 'be quiet!', 'NZXT'],
    brandStrict: false
  },
  case: {
    brands: ['Lian Li', 'Fractal Design', 'NZXT', 'Cooler Master', 'Corsair', 'Antec', 'SAMA'],
    brandStrict: false
  },
  other: {
    brands: [],
    brandStrict: false
  }
}

// 一行里「算填过了」的字段。状态、币种这些一建行就有默认值的不算，否则六个默认槽位
// 一摆出来就全成了「有内容」，会被原样存进库，部件数从此显示成 0/6。
const CONTENT_KEYS = [
  'brand', 'model', 'spec', 'serial_no', 'note',
  'sale_date', 'sale_amount', 'domestic_shipping_amount'
]

// 这一行填过东西没有。**只看内容**，用于界面上标「未填写」。
export function hasPartContent(part) {
  return CONTENT_KEYS.some((key) => {
    const value = part[key]
    return value !== null && value !== undefined && value !== ''
  })
}

// 这一行要不要提交给后端。注意它和 hasPartContent 不是一回事：
//
//   _keep        —— 这一行是真实存在的：从服务端载入的（库里就有它）、用户自己点
//                   「添加部件」加的、或为了传图刚建出来的。这类行只有用户点「删除
//                   该部件」才会消失，清空文字不会——不然改着改着图片就被级联删了。
//   _media_count —— 传过图，同上。
//   有内容       —— 默认摆出来的六个槽位只是录入模板，填了才落库。
//
// 详情页据此决定提交不提交；判断只此一处，两边不一致就会出现部件莫名多出来或消失。
export function isBlankPart(part) {
  if (part._keep || part._media_count) return false
  return !hasPartContent(part)
}

export function partSchema(partType) {
  return PART_SCHEMA[partType] || PART_SCHEMA.other
}

// 「规格」这一栏的标题按类型换（核心编号 / 容量 / 功率 / 芯片组…），i18n 里对应
// partSpec.<type>；没有单独定义的类型退回 partSpec.other。
export function specLabelKey(partType) {
  return 'partSpec.' + (PART_SCHEMA[partType] ? partType : 'other')
}
