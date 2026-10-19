<script setup lang="ts">
import { ref, watch } from 'vue'
import { Download, FileText } from 'lucide-vue-next'
import { api, fileUrl, sessionUrl } from '../api/client'
import type { Attachment, Preview } from '../types'
const props = defineProps<{ item: Attachment; sid: string }>()
const image = ref('')
watch(() => [props.sid, props.item.path], async (_, __, onCleanup) => {
  let valid = true; onCleanup(() => { valid = false }); image.value = ''
  if (props.item.image) {
    try { const result = await api<Preview>(`${sessionUrl(props.sid,'preview')}?path=${encodeURIComponent(props.item.path)}`); if(valid) image.value=result.image } catch { /* download still available */ }
  }
}, { immediate: true })
</script>
<template><a class="attachment-card" :href="fileUrl(sid,item.path)" download><img v-if="image" :src="image" :alt="item.name" /><FileText v-else :size="23" /><span>{{ item.name }}<small>{{ (item.size/1024).toFixed(1) }} KB</small></span><Download :size="14" /></a></template>
