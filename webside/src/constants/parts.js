// 部件类型各自的品牌候选。
//
// 为什么要分类型：CPU 的品牌只可能是 Intel / AMD，硬盘和主板则完全是另一批厂商。
// 一个统一的品牌文本框等于每次都靠人自己回忆并手打，几台机器之后同一个厂商就会有
// 三种写法，之后想按品牌归类就全乱了。
//
// 候选值一律用拉丁写法（ASUS、Kingston、Seasonic），三种界面语言下都不用翻译，也和
// 日本站上的原始标注对得上。除 CPU 外都允许现场输入清单外的值（filterable +
// allow-create），清单只是省事的默认项，不是白名单。

// 新建整机时默认列出的六个部件槽位，顺序即表单里的显示顺序。
// 这六样是一台机器几乎必然有的东西，不该让人每次都点六下「快捷添加」。
export const DEFAULT_PART_TYPES = ['cpu', 'gpu', 'ram', 'disk', 'motherboard', 'psu']

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

// 一行里「算填过了」的字段。数量、状态、币种这些一建行就有默认值的不算，否则六个
// 默认槽位一摆出来就全成了「有内容」，会被原样存进库，部件数从此显示成 0/6。
const CONTENT_KEYS = [
  'brand', 'model', 'spec', 'serial_no', 'note',
  'sale_date', 'sale_amount', 'domestic_shipping_amount'
]

// 完全没填过的槽位。详情页据此决定「这一行提交不提交」，部件卡据此把它画淡一档
// ——两边必须是同一条判断：卡片显示「未填写」而保存时却提交了它（或反过来），
// 表现就是部件莫名其妙地多出来或者消失。
export function isBlankPart(part) {
  // 传了图也算「有内容」：否则把文字清空的那一刻这一行会被当成空槽位不再提交，
  // 后端随即删掉它，挂在上面的图片跟着级联消失。
  if (part._media_count) return false
  return !CONTENT_KEYS.some((key) => {
    const value = part[key]
    return value !== null && value !== undefined && value !== ''
  })
}

export function partSchema(partType) {
  return PART_SCHEMA[partType] || PART_SCHEMA.other
}

// 「规格」这一栏的标题按类型换（显存 / 容量 / 功率 / 芯片组…），i18n 里对应
// partSpec.<type>；没有单独定义的类型退回 partSpec.other。
export function specLabelKey(partType) {
  return 'partSpec.' + (PART_SCHEMA[partType] ? partType : 'other')
}
