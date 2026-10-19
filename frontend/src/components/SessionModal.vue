<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Archive, Download } from 'lucide-vue-next'
import ModalShell from './ModalShell.vue'
import { useDesk } from '../stores/desk'
import { api, body } from '../api/client'
const desk=useDesk(), router=useRouter(), title=ref(desk.session!.title)
const id=desk.session!.id
function rename(){desk.guard(async()=>{await api(`/sessions/${id}`,{method:'PATCH',body:body({title:title.value})});await desk.refreshSessions();desk.dialog=null})}
function archive(){desk.guard(async()=>{await api(`/sessions/${id}`,{method:'PATCH',body:body({archived:true})});await desk.refreshSessions();const next=desk.sessions[0]?.id;desk.dialog=next?null:'new-project';await router.push(next?`/chat/${next}`:'/')})}
</script>
<template><ModalShell title="作品管理" @close="desk.dialog=null"><form @submit.prevent="rename"><label>作品名称<input v-model="title" required maxlength="100" /></label><button class="primary" :disabled="!title.trim()">保存名称</button></form><div class="export-links"><a class="secondary" :href="`/api/sessions/${id}/export?format=md`" download><Download :size="16" />保存聊天记录</a></div><div class="archive-section"><p>收起来以后，仍然可以在左边找回来。</p><button class="secondary" :disabled="desk.locked" @click="archive"><Archive :size="16" />把作品收起来</button></div></ModalShell></template>
