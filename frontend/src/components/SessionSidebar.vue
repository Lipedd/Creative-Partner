<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Archive, Folder, MessageSquare, Plus, Search, Settings2, X } from 'lucide-vue-next'
import { useDesk } from '../stores/desk'
import { api, body } from '../api/client'
import type { Session } from '../types'
const desk = useDesk(), router = useRouter(), query = ref('')
const filtered = computed(() => desk.sessions.filter(s => s.title.toLowerCase().includes(query.value.toLowerCase())))
function create() { desk.projectDraft='';desk.projectNameDraft='';desk.dialog='new-project' }
function open(s: Session) { desk.guard(async () => {
  if (s.archived) { await api(`/sessions/${s.id}`, { method: 'PATCH', body: body({ archived: false }) }); desk.archived = false; await desk.refreshSessions() }
  await router.push(`/chat/${s.id}`)
}) }
</script>
<template>
  <aside class="sidebar" :class="{ open: desk.sidebarOpen }">
    <div class="brand"><span class="brand-icon"><img src="/brand-dolphin.png" alt="" /></span><div>创想伙伴<small>把点子变成作品</small></div><button class="icon-button mobile-only" aria-label="收起导航" @click="desk.sidebarOpen=false"><X :size="18" /></button></div>
    <button class="primary new-chat" @click="create"><Plus :size="18" />新建对话</button>
    <div class="section-label">{{ desk.archived ? '收起来的对话' : '最近的对话' }}<span>{{ filtered.length }}</span></div>
    <div class="search-field"><Search :size="15" /><input v-model="query" aria-label="搜索对话" placeholder="找一找对话…" /></div>
    <nav class="sessions"><button v-for="s in filtered" :key="s.id" class="session-row" :class="{ selected: desk.session?.id === s.id }" @click="open(s)"><Folder v-if="s.project" :size="16" /><MessageSquare v-else :size="16" /><span>{{ s.title }}</span><i v-if="s.running" class="status-dot pulse" /><i v-else-if="s.pending" class="status-dot amber" /></button><p v-if="!filtered.length" class="empty-small">{{ query ? '没有找到这个对话' : '还没有对话' }}</p></nav>
    <footer class="sidebar-footer"><button class="nav-action" @click="desk.archived=!desk.archived; desk.guard(desk.refreshSessions)"><Archive :size="17" />{{ desk.archived ? '返回最近对话' : '收起来的对话' }}</button><button v-if="!desk.demo.enabled" class="nav-action" @click="desk.dialog='settings'"><Settings2 :size="17" />模型配置</button><p v-else class="demo-sidebar-note">体验内容会在 60 分钟后自动清除。喜欢的话，可以在 GitHub 下载完整版。</p></footer>
  </aside>
</template>
