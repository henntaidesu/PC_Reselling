<template>
  <div class="media-gallery">
    <div v-if="!hostingConfigured" class="hint warn">{{ t('media.notConfigured') }}</div>

    <div v-else class="grid" :class="{ 'grid--lg': large }">
      <div v-for="item in items" :key="item.id" class="cell">
        <div class="thumb" @click="preview(item)">
          <img v-if="item.kind === 'image'" :src="thumbUrl(item)" :alt="item.filename" loading="lazy" />
          <div v-else class="video-thumb">
            <el-icon :size="20"><VideoPlay /></el-icon>
            <span class="video-tag">{{ t('media.video') }}</span>
          </div>
        </div>
        <button class="del-btn" type="button" :title="t('common.delete')" @click.stop="removeItem(item)">
          <el-icon><Close /></el-icon>
        </button>
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
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Close, Plus, VideoPlay } from '@element-plus/icons-vue'
import { mediaApi } from '@/api'
import { ElMessage } from '@/utils/notify'

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
  large: { type: Boolean, default: false }
})
const emit = defineEmits(['changed'])

const { t } = useI18n()

const items = ref([])
const uploading = ref(false)
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

function onPick(file) {
  if (uploading.value) return
  pending.push(file.raw)
  if (!flushScheduled) {
    flushScheduled = true
    queueMicrotask(flush)
  }
}

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
.uploader :deep(.el-upload) { width: 100%; display: block; }
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
