<template>
  <div class="part-media">
    <!-- 文件是挂在部件行上的，行还没存进库就没有 id，无处可挂。这一行只要填了任何
         内容，600ms 后的自动保存就会把它建出来，提示随即消失。 -->
    <div v-if="!partId" class="hint">{{ t('device.mediaNeedSave') }}</div>
    <div v-else-if="!hostingConfigured" class="hint warn">{{ t('media.notConfigured') }}</div>

    <div v-else class="grid">
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

const props = defineProps({
  // 部件还没保存时为 null：此时只显示提示，不给上传口
  partId: { type: [Number, null], default: null },
  hostingConfigured: { type: Boolean, default: true }
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
  if (!props.partId) {
    items.value = []
    return
  }
  try {
    const res = await mediaApi.listForPart(props.partId)
    items.value = res.items || []
  } catch {
    items.value = []
  }
}

// 部件是懒加载的（展开那一栏才挂载），partId 也可能从 null 变成真实 id（刚保存完），
// 两种情况都要重新拉一次
watch(() => props.partId, load, { immediate: true })

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
  if (uploading.value || !props.partId) return
  pending.push(file.raw)
  if (!flushScheduled) {
    flushScheduled = true
    queueMicrotask(flush)
  }
}

async function flush() {
  flushScheduled = false
  const files = pending.splice(0)
  if (!files.length || !props.partId) return

  uploading.value = true
  try {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    const res = await mediaApi.uploadForPart(props.partId, fd)
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
    await mediaApi.removePartMedia(item.id, true)
    await load()
    emit('changed', items.value.length)
    ElMessage.success(t('common.deleted'))
  } catch {
    // 拦截器已提示
  }
}
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

/* 部件的图比卡片少得多，格子小一档，一行能排开也不至于把表单撑长 */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  gap: 8px;
}
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
