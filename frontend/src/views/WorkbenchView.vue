<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ExternalLink, LoaderCircle, Menu, MoreHorizontal, PanelRight, X } from 'lucide-vue-next'
import SessionSidebar from '../components/SessionSidebar.vue'
import ChatPanel from '../components/ChatPanel.vue'
import WorkspaceInspector from '../components/WorkspaceInspector.vue'
import SettingsModal from '../components/SettingsModal.vue'
import NewProjectModal from '../components/NewProjectModal.vue'
import SessionModal from '../components/SessionModal.vue'
import { useDesk } from '../stores/desk'
const desk=useDesk(), route=useRoute(), router=useRouter(), booted=ref(false)
async function selectRoute(id:unknown) {
  await desk.guard(async()=>{
    if(typeof id==='string' && id) await desk.select(id)
    else if(desk.sessions[0]) await router.replace(`/chat/${desk.sessions[0].id}`)
    else desk.dialog='new-project'
  })
}
onMounted(async()=>{await desk.guard(desk.initialize);booted.value=true;await selectRoute(route.params.id)})
watch(()=>route.params.id,id=>{if(booted.value) void selectRoute(id)})
function keyboard(e:KeyboardEvent) {if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='n'){e.preventDefault();desk.dialog='new-project'}}
function responsive(){if(window.innerWidth<760){desk.inspectorOpen=false;desk.sidebarOpen=false}}
onMounted(()=>{window.addEventListener('keydown',keyboard);window.addEventListener('resize',responsive);responsive()})
onUnmounted(()=>{desk.dispose();window.removeEventListener('keydown',keyboard);window.removeEventListener('resize',responsive)})
</script>
<template>
  <div class="workbench" :class="{'inspector-closed':!desk.inspectorOpen}"><button v-if="desk.sidebarOpen" class="sidebar-overlay" aria-label="关闭导航" @click="desk.sidebarOpen=false" /><SessionSidebar />
    <main class="main-workspace"><header class="topbar"><div class="title-group"><button class="icon-button mobile-only" aria-label="展开导航" @click="desk.sidebarOpen=true"><Menu :size="20" /></button><span class="breadcrumb">我的作品 <span>/</span></span><h2>{{ desk.session?.title || '创想伙伴' }}</h2></div><div class="topbar-actions"><a v-if="desk.session?.project?.preview_ready" class="open-project-button" :href="desk.session.project.preview_url" target="_blank"><ExternalLink :size="15" />打开我的作品</a><button class="icon-button" aria-label="作品管理" :disabled="!desk.session" @click="desk.dialog='session'"><MoreHorizontal :size="20" /></button><button class="icon-button" :class="{ selected:desk.inspectorOpen }" aria-label="查看作品内容" @click="desk.inspectorOpen=!desk.inspectorOpen"><PanelRight :size="19" /></button></div></header>
      <div class="workspace-body"><section class="chat-column"><div class="chat-topline"><span class="tag">创作伙伴</span><button v-if="desk.session" class="model-button" @click="desk.dialog='settings'">模型配置</button></div><div v-if="desk.loading || (!desk.state && !desk.error && !!desk.sessions.length)" class="loading-state"><LoaderCircle class="spin" :size="23" />正在打开作品…</div><ChatPanel v-else-if="desk.state" :key="desk.session?.id" /><div v-else class="loading-state">点击“新建作品”，告诉我你的新点子。</div></section><WorkspaceInspector v-if="desk.session && desk.inspectorOpen" /></div>
    </main>
    <div v-if="desk.error" class="error-toast" role="alert"><span>{{ desk.error }}</span><button class="icon-button" aria-label="关闭错误提示" @click="desk.error=''"><X :size="16" /></button></div>
    <SettingsModal v-if="desk.dialog==='settings'" /><NewProjectModal v-if="desk.dialog==='new-project'" /><SessionModal v-if="desk.dialog==='session' && desk.session" />
  </div>
</template>
