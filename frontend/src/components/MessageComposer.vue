<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUp, LoaderCircle, Paperclip, Settings2, Square, X } from 'lucide-vue-next'
import { useDesk } from '../stores/desk'
import { api, sessionUrl } from '../api/client'
import type { Attachment } from '../types'
const desk = useDesk(), text = ref(desk.state?.messages.length ? '' : (desk.session?.project?.idea ?? '')), attachments = ref<Attachment[]>([]), uploading = ref(false), dragging = ref(false)
const projectMode=computed(()=>!!desk.session?.project)
const picker = ref<HTMLInputElement>()
async function upload(files: FileList | File[]) {
  if (!desk.session || desk.locked || uploading.value) return
  const list = Array.from(files)
  if (list.length + attachments.value.length > 8) { desk.error = '每条消息最多 8 个附件'; return }
  if (list.some(f => f.size > 20*1024*1024)) { desk.error = '单个附件不能超过 20 MB'; return }
  const sid = desk.session.id
  uploading.value = true
  await desk.guard(async () => {
    const data = new FormData(); list.forEach(f => data.append('files', f))
    const result = await api<Attachment[]>(sessionUrl(sid,'uploads'), { method: 'POST', body: data })
    attachments.value.push(...result); desk.refreshFiles++
  })
  uploading.value = false
  if (picker.value) picker.value.value = ''
}
async function send() {
  if (desk.locked || desk.sending || uploading.value || !desk.ready || (!text.value.trim() && !attachments.value.length)) return
  const sent = await desk.guard(() => desk.send(text.value, attachments.value))
  if (sent) { text.value=''; attachments.value=[] }
}
function keydown(e: KeyboardEvent) { if(e.key==='Enter' && !e.shiftKey && !e.isComposing) {e.preventDefault(); void send()} }
function paste(e: ClipboardEvent) { const files=Array.from(e.clipboardData?.files ?? []); if(files.length) {e.preventDefault(); void upload(files)} }
function drop(e: DragEvent) { dragging.value=false; if(e.dataTransfer?.files.length) void upload(e.dataTransfer.files) }
defineExpose({ setText: (value: string) => { text.value=value } })
</script>
<template>
  <div class="composer-wrap">
    <button v-if="!desk.ready" class="setup-notice" @click="desk.dialog='settings'"><Settings2 :size="16" />请进行模型配置 <span>去配置 →</span></button>
    <div class="composer" :class="{ dragging }" @dragover.prevent="dragging=true" @dragleave.prevent="dragging=false" @drop.prevent="drop">
      <div v-if="attachments.length" class="pending-attachments"><span v-for="(a,i) in attachments" :key="a.path"><Paperclip :size="13" />{{ a.name }}<button :aria-label="`移除 ${a.name}`" @click="attachments.splice(i,1)"><X :size="13" /></button></span></div>
      <textarea v-model="text" :aria-label="projectMode?'告诉创作伙伴你的想法':'和创作伙伴聊天'" :placeholder="projectMode?'说说你想增加什么，图片和文件也可以直接放进来…':'想聊什么就打在这里…'" :disabled="desk.locked || desk.sending" @keydown="keydown" @paste="paste" />
      <div class="composer-toolbar"><div class="composer-options"><button class="icon-button" title="放入图片或文件" aria-label="放入图片或文件" :disabled="uploading || desk.locked" @click="picker?.click()"><LoaderCircle v-if="uploading" class="spin" :size="18" /><Paperclip v-else :size="18" /></button><input ref="picker" type="file" multiple hidden @change="e => {const f=(e.target as HTMLInputElement).files; if(f) upload(f)}" /></div>
        <button v-if="desk.running" class="send-button stop" aria-label="停止生成" @click="desk.guard(() => api(sessionUrl(desk.session!.id,'stop'), {method:'POST'}))"><Square :size="16" fill="currentColor" /></button>
        <button v-else class="send-button" :aria-label="projectMode && !desk.state?.messages.length?'开始制作':'发送'" :title="projectMode && !desk.state?.messages.length?'开始制作':'发送'" :disabled="!desk.ready || desk.locked || uploading || desk.sending || (!text.trim() && !attachments.length)" @click="send"><LoaderCircle v-if="desk.sending" class="spin" :size="19" /><ArrowUp v-else :size="20" /></button>
      </div>
    </div><div class="composer-hint"><span>{{ projectMode && !desk.state?.messages.length ? '想法已经放好了，点箭头开始制作' : '按 Enter 发送' }}</span><span>可以放入图片和文件</span></div>
  </div>
</template>
