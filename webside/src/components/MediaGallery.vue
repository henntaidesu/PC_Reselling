<template>
  <div class="media-gallery">
    <div v-if="!hostingConfigured" class="hint warn">{{ t('media.notConfigured') }}</div>

    <div v-else class="drop-zone" :class="{ dropping: dragging }" v-on="dropHandlers">
      <div class="grid" :class="{ 'grid--lg': large }">
        <!-- draggable 挂在格子上，图片本身 draggable="false"：不然拖起来的是那张 img
             自己（浏览器默认行为），我们的 dragstart 根本不会触发 -->
        <div
          v-for="item in visibleItems"
          :key="item.id"
          class="cell"
          :class="sort.cellClass(item)"
          draggable="true"
          :title="t('media.dragToSort')"
          v-on="sort.handlers(items, item)"
        >
          <div class="thumb" @click="preview(item)">
            <img v-if="item.kind === 'image'" :src="thumbUrl(item)" :alt="item.filename"
                 loading="lazy" draggable="false" />
            <div v-else class="video-thumb">
              <el-icon :size="20"><VideoPlay /></el-icon>
              <span class="video-tag">{{ t('media.video') }}</span>
            </div>
          </div>
          <button class="del-btn" type="button" :title="t('common.delete')" @click.stop="removeItem(item)">
            <el-icon><Close /></el-icon>
          </button>
          <!-- 「设为封面」只在触屏上出现（样式里的 @media (hover: none)）：那边没有拖拽
               排序，而第一张图就是列表里的封面。桌面端拖一下就行，不用多这个按钮。 -->
          <button class="cover-btn" type="button" :title="t('media.setCover')"
            @click.stop="sort.moveToFront(items, item)">
            <el-icon><Star /></el-icon>
          </button>
        </div>

        <!-- 装不下的那些收在这里：让缩略图把卡片撑到比表单还长，不如点一下再展开 -->
        <div v-if="hiddenCount" class="more-cell" @click="expanded = true">
          <span class="more-n">+{{ hiddenCount }}</span>
          <span>{{ t('media.more') }}</span>
        </div>

        <el-upload
          :show-file-list="false"
          :auto-upload="false"
          :multiple="true"
          :disabled="uploading"
          accept="image/*,video/*"
          class="uploader"
          :on-change="onPick"
        >
          <div class="add-cell" :class="{ disabled: uploading }">
            <el-icon :size="18"><Plus /></el-icon>
            <span>{{ uploading ? t('media.uploading') : t('media.upload') }}</span>
          </div>
        </el-upload>
      </div>

      <!-- 遮罩必须 pointer-events: none，不然它一浮出来就顶替了鼠标下方的元素，
           dragleave / dragenter 会打成一片 -->
      <div v-if="dragging" class="drop-mask">{{ t('media.dropHere') }}</div>
    </div>

    <div v-if="expanded && overLimit" class="collapse-row">
      <el-button link size="small" @click="expanded = false">{{ t('media.collapse') }}</el-button>
    </div>

    <el-image-viewer
      v-if="viewerUrls.length"
      :url-list="viewerUrls"
      :initial-index="viewerIndex"
      hide-on-click-modal
      @close="viewerUrls = []"
    />
    <el-dialog v-model="videoDialog" width="720px" append-to-body class="video-dialog">
      <video v-if="videoUrl" :src="videoUrl" controls autoplay class="video-player" />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Close, Plus, Star, VideoPlay } from '@element-plus/icons-vue'
import { mediaApi } from '@/api'
import { ElMessage } from '@/utils/notify'
import { useFileDrop } from '@/composables/useFileDrop'
import { useMediaSort } from '@/composables/useMediaSort'

// 平铺一组图，不分类。两种归属共用这一个组件：owner='parts' 挂在某个部件上，
// owner='devices' 挂在整机本身上（整机外观 / 铭牌 / 开机测试这类照片）。
// 显卡不走这里——它的图分五类，用 MediaManager。
const props = defineProps({
  owner: { type: String, required: true },   // 'parts' | 'devices'
  // 归属行还没存进库时为 null。此时不是禁用上传，而是先调 ensureId 把行建出来——
  // 「想给这条内存拍的照片先存下来」是个完全正当的诉求，不该被「你得先填点什么」挡住。
  ownerId: { type: [Number, null], default: null },
  ensureId: { type: Function, default: null },
  hostingConfigured: { type: Boolean, default: true },
  large: { type: Boolean, default: false },
  // 最多平铺几张，多出来的收进「更多图片」。0 = 不限制（整机那份图就不限）。
  limit: { type: Number, default: 0 }
})
const emit = defineEmits(['changed'])

const { t } = useI18n()

const items = ref([])
const expanded = ref(false)
const uploading = ref(false)

const overLimit = computed(() => props.limit > 0 && items.value.length > props.limit)
const hiddenCount = computed(() =>
  overLimit.value && !expanded.value ? items.value.length - props.limit : 0
)
const visibleItems = computed(() =>
  hiddenCount.value ? items.value.slice(0, props.limit) : items.value
)
const viewerUrls = ref([])
const viewerIndex = ref(0)
const videoDialog = ref(false)
const videoUrl = ref('')

// 一次拖多个文件时 el-upload 会逐个触发 on-change。攒进 buffer，用 microtask 合并成
// 一次批量上传，而不是每个文件打一次接口。
const pending = []
let flushScheduled = false

async function load() {
  if (!props.ownerId) {
    items.value = []
    return
  }
  try {
    const res = await mediaApi.flatList(props.owner, props.ownerId)
    items.value = res.items || []
  } catch {
    items.value = []
  }
}

// 归属 id 可能从 null 变成真实 id（刚为了传图建出来），要重新拉一次
watch(() => [props.owner, props.ownerId], load, { immediate: true })

function thumbUrl(item) {
  // 图床支持 ?w=<档位> 缩略图，列表里用 400 宽的，省流量
  return item.public_url + (item.public_url.includes('?') ? '&' : '?') + 'w=400'
}

function preview(item) {
  if (item.kind === 'video') {
    videoUrl.value = item.public_url
    videoDialog.value = true
    return
  }
  const images = items.value.filter((m) => m.kind === 'image')
  viewerUrls.value = images.map((m) => m.public_url)
  viewerIndex.value = Math.max(0, images.findIndex((m) => m.id === item.id))
}

function queue(files) {
  if (uploading.value || !files.length) return
  pending.push(...files)
  if (!flushScheduled) {
    flushScheduled = true
    queueMicrotask(flush)
  }
}

function onPick(file) {
  queue([file.raw])
}

// 拖进来的和点进来的走同一条管线（同样攒进 buffer 合并成一次请求）
const { dragging, handlers: dropHandlers } = useFileDrop(
  (files, rejected) => {
    if (rejected) ElMessage.warning(t('media.dropRejected', { n: rejected }))
    queue(files)
  },
  { disabled: () => uploading.value || !props.hostingConfigured }
)

async function flush() {
  flushScheduled = false
  const files = pending.splice(0)
  if (!files.length) return

  uploading.value = true
  try {
    // 行还没建出来（比如刚摆出来的空部件槽位）：先让页面存一次拿到 id 再传。
    // 用 ensureId 的返回值而不是 props.ownerId——props 要等父组件那一轮渲染才更新。
    let id = props.ownerId
    if (!id && props.ensureId) id = await props.ensureId()
    if (!id) return

    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    const res = await mediaApi.flatUpload(props.owner, id, fd)
    await load()
    emit('changed', items.value.length)
    if (res.errors?.length) {
      ElMessage.warning(t('media.partialFail', { ok: res.uploaded.length, fail: res.errors.length }))
    } else {
      ElMessage.success(t('media.uploaded', { n: res.uploaded.length }))
    }
  } catch {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
}

// 拖拽排序。本地顺序已经改了，这里只负责落库；存不上就把服务端的顺序拉回来——
// 界面上留着一个其实没生效的排序，比排序失败本身更糟。
const sort = useMediaSort(async (ids) => {
  try {
    await mediaApi.flatReorder(props.owner, props.ownerId, ids)
  } catch {
    await load()   // 拦截器已提示
  }
})

async function removeItem(item) {
  try {
    await mediaApi.flatRemove(props.owner, item.id, true)
    await load()
    emit('changed', items.value.length)
    ElMessage.success(t('common.deleted'))
  } catch {
    // 拦截器已提示
  }
}

defineExpose({ reload: load })
</script>

<style scoped>
.hint {
  font-size: 12px;
  color: #8a94a6;
  padding: 10px 12px;
  border: 1px dashed #3a4a66;
  border-radius: 8px;
  background: rgba(91, 140, 255, 0.03);
}
.hint.warn { color: #e6a23c; border-color: #6b5326; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  gap: 8px;
}
/* 整机自己的照片给大一档：那是「这台机器长什么样」，缩略图太小等于没有 */
.grid--lg { grid-template-columns: repeat(auto-fill, minmax(132px, 1fr)); gap: 10px; }
.cell {
  position: relative;
  aspect-ratio: 4 / 3;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #28354a;
  background: #0e1830;
}
.thumb { width: 100%; height: 100%; cursor: pointer; }
/* 拖动中的那张淡下去，插入位置在目标格子的对应一侧画一条竖线。
   竖线画在格子**内侧**：.cell 是 overflow: hidden（圆角要靠它裁图），画在外面会被裁掉 */
.cell.sorting { opacity: 0.35; }
.cell.sort-before::after,
.cell.sort-after::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  width: 3px;
  background: #5b8cff;
  z-index: 2;
}
.cell.sort-before::after { left: 0; }
.cell.sort-after::after { right: 0; }
.thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
.video-thumb {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: #8fb8ff;
}
.video-tag { font-size: 11px; color: #a6adb4; }
.del-btn {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 12px;
}
.del-btn:hover { background: #f87171; }
/* 「设为封面」。平时不存在：桌面端拖一下就换了封面，多一个按钮只是噪点。 */
.cover-btn {
  display: none;
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #ffd66b;
  align-items: center;
  justify-content: center;
}

@media (hover: none) {
  /* 触屏上这两个角标都要能按得中。18~22px 见方在手机上是「点三次中一次」的尺寸，
     而它俩紧挨着缩略图——点空了就落到下面那层 .thumb 上，本想删一张图，结果弹出了
     全屏预览；反过来想看大图却把它删了。撑到 28px，两个角各占一边，不再打架。 */
  .del-btn, .cover-btn { width: 28px; height: 28px; }
  .cover-btn { display: flex; }
  /* 第一张本来就是封面，不给按钮——按了什么也不会变，反而让人以为没生效 */
  .cell:first-child .cover-btn { display: none; }
}

/* 「更多图片」和上传格子长一个样：它俩都是格子，不是按钮 */
.more-cell {
  aspect-ratio: 4 / 3;
  border: 1px dashed #3a4a66;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: #8a94a6;
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.more-cell:hover { border-color: #5b8cff; color: #8fb8ff; }
.more-n { font-size: 15px; color: #8fb8ff; }
.collapse-row { margin-top: 6px; text-align: center; }
.uploader :deep(.el-upload) { width: 100%; display: block; }

/* 撑满外面那张卡（配合 App.vue 里 .pcr-split-media 的两条规则）。父级不是 flex 时
   flex 属性会被忽略，退回按内容高度排，所以放在别处用也不会错位 */
.media-gallery { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }

/* 投放区：平时完全看不出来，拖着文件进来才浮出边框 + 遮罩。
   flex: 1 是为了让它吃掉卡片里剩余的空白——「整张卡都能拖进来」要的就是这一段，
   否则能放的只有缩略图占住的那一行 */
.drop-zone { position: relative; border-radius: 10px; flex: 1 1 auto; }
.drop-zone.dropping { outline: 2px dashed #5b8cff; outline-offset: 4px; }
.drop-mask {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(11, 18, 32, 0.82);
  color: #8fb8ff;
  font-size: 13px;
  pointer-events: none;
}
.add-cell {
  aspect-ratio: 4 / 3;
  border: 1px dashed #3a4a66;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: #8a94a6;
  font-size: 11px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
}
.add-cell:hover { border-color: #5b8cff; color: #8fb8ff; }
.add-cell.disabled { opacity: 0.5; cursor: not-allowed; }
.video-player { width: 100%; max-height: 70vh; border-radius: 8px; }
</style>
