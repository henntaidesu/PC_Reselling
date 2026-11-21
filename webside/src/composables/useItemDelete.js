import { h, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { jpy } from '@/utils/format'
import { ElMessage } from '@/utils/notify'

// 详情弹窗里的「删除这一件」，显卡与整机共用。
//
// 钱的部分全在后端：删货时扣款与出售回流由外键级联带走，随后整体重算资金池
// （cards_api.delete_card / devices_api.delete_device），扣掉的钱就这样回到了归属人的池里。
// 前端要管的是三件事，每一件漏了都不报错、只是结果不对：
//
// 1. 确认框里把「钱会怎么动」说清楚。删一件走池子的货不只是删一行——池子按 FIFO 重排，
//    别的货的成本会跟着变；删一件以日元卖掉的货，回流进池的那笔注资也一起撤掉。
// 2. 先等完在途的自动保存再删。否则 PUT 晚于 DELETE 落地，拦截器冒一个 404；顺带也让
//    确认框里的金额是存完之后的最新值，而不是改价之前的。
// 3. 删完关弹窗走的仍是列表页路由守卫里的 beforeClose，它得知道这一件已经没了，
//    不能再去 flush 或删草稿——removed 就是给它看的。
//
// 用法：
//   const del = useItemDelete({ autosave, snapshot: () => card.value, label: () => '…',
//     remove: () => cardsApi.remove(id), onRemoved: () => emit('close') })
//   beforeClose 里先 if (del.removed.value) return
export function useItemDelete({ autosave, snapshot, label, remove, onRemoved }) {
  const { t } = useI18n()
  const removing = ref(false)
  const removed = ref(false)

  const total = (rows) => (rows || []).reduce((s, r) => s + (Number(r.amount) || 0), 0)

  function message(item) {
    const lines = [t('detail.deleteConfirm', { name: label() })]
    // 扣款按全额退：欠款（shortfall）本来就从余额里减掉了，删掉扣款后余额回升的正是整笔
    const drawn = total(item.fund_draws)
    if (drawn > 0) {
      lines.push(t('detail.deletePoolBack', { name: item.fund_draws[0].contributor || '', amount: jpy(drawn) }))
    }
    const returned = total(item.fund_returns)
    if (returned > 0) lines.push(t('detail.deleteSaleBack', { amount: jpy(returned) }))
    return h('div', lines.map((line) => h('p', { style: 'margin: 0 0 6px; line-height: 1.6' }, line)))
  }

  async function run() {
    if (removing.value || !snapshot()) return
    if (autosave.pending.value) {
      try { await autosave.flush() } catch { return }
    }
    try {
      await ElMessageBox.confirm(message(snapshot()), t('common.delete'), {
        type: 'warning',
        confirmButtonText: t('common.delete'),
        confirmButtonClass: 'el-button--danger'
      })
    } catch {
      return
    }
    removing.value = true
    // 请求往返期间再敲的字不能触发保存：那一行马上就不存在了
    autosave.pause()
    try {
      await remove()
      removed.value = true
      ElMessage.success(t('common.deleted'))
      onRemoved()
    } catch {
      // 拦截器已提示；没删成就接着自动保存
      await autosave.begin()
    } finally {
      removing.value = false
    }
  }

  return { removing, removed, run }
}
