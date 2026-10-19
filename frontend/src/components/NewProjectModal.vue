<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowUp, ChevronRight, Folder, FolderHeart, HardDrive, LoaderCircle, Sparkles } from 'lucide-vue-next'
import ModalShell from './ModalShell.vue'
import { useDesk } from '../stores/desk'
import { api } from '../api/client'
import type { Directories } from '../types'

const desk=useDesk(), router=useRouter(), step=ref<1|2|3>(1), idea=ref(''), path=ref(desk.workspace), listing=ref<Directories>(), busy=ref(false), error=ref('')
function next(){if(idea.value.trim()) step.value=2}
async function browse(value=path.value){busy.value=true;error.value='';try{listing.value=await api<Directories>(`/directories?path=${encodeURIComponent(value)}`);path.value=listing.value.path}catch(e){error.value=e instanceof Error?e.message:'这里暂时打不开'}finally{busy.value=false}}
async function create(placement:'auto'|'manual') {busy.value=true;error.value='';try{const id=await desk.createProject(idea.value,placement,placement==='manual'?path.value:undefined);desk.dialog=null;await router.push(`/chat/${id}`)}catch(e){error.value=e instanceof Error?e.message:'作品没有建好，再试一次吧'}finally{busy.value=false}}
function manual(){step.value=3;void browse()}
onMounted(()=>{document.getElementById('project-idea')?.focus()})
</script>
<template><ModalShell title="开始一个新作品" :subtitle="step===1?'先说说你想做什么，剩下的交给我。':step===2?'选择作品放在哪里。推荐让我自动准备。':'选择一个你熟悉的文件夹。'" @close="desk.dialog=null">
  <form v-if="step===1" class="idea-step" @submit.prevent="next"><label for="project-idea">今天你想做什么？</label><textarea id="project-idea" v-model="idea" maxlength="4000" placeholder="比如：我想做一个双人坦克游戏，两个人都能移动和放技能！" /><p>不用想得很完整，想到什么就说什么。</p><div class="modal-actions"><span /><button class="primary" :disabled="!idea.trim()">下一步 <ChevronRight :size="16" /></button></div></form>
  <div v-else-if="step===2"><div class="placement-grid"><button class="placement-card recommended" :disabled="busy" @click="create('auto')"><span><Sparkles :size="25" /></span><strong>帮我准备好 <i>推荐</i></strong><p>我会自动取名字、建好位置，马上开始制作。</p><ChevronRight :size="18" /></button><button class="placement-card" :disabled="busy" @click="manual"><span><FolderHeart :size="25" /></span><strong>我自己选择位置</strong><p>如果你已经准备好了文件夹，可以选它。</p><ChevronRight :size="18" /></button></div><div v-if="busy" class="creating-note"><LoaderCircle class="spin" :size="17" />正在准备你的作品…</div><div v-if="error" class="inline-error">{{ error }}</div><div class="modal-actions"><button class="secondary" @click="step=1"><ArrowLeft :size="15" />返回修改想法</button></div></div>
  <div v-else><form class="path-form" @submit.prevent="browse()"><label for="project-path">你选择的位置</label><div><input id="project-path" v-model="path" /><button class="secondary" :disabled="busy">打开</button></div></form><div class="directory-controls"><button class="text-button" :disabled="busy || !listing || listing.path===listing.parent" @click="browse(listing?.parent)"><ArrowUp :size="15" />上一级</button><button v-for="root in listing?.roots" :key="root" class="text-button" :disabled="busy" @click="browse(root)"><HardDrive :size="14" />{{ root }}</button></div><div class="directory-list"><button v-for="dir in listing?.directories" :key="dir.path" :disabled="busy" @click="browse(dir.path)"><Folder :size="19" /><span>{{ dir.name }}</span><ChevronRight :size="16" /></button><p v-if="!listing?.directories.length" class="empty-small">这里没有别的文件夹，可以直接选择这里。</p></div><div v-if="error" class="inline-error">{{ error }}</div><div class="modal-actions"><button class="secondary" @click="step=2"><ArrowLeft :size="15" />返回</button><button class="primary" :disabled="busy" @click="create('manual')"><LoaderCircle v-if="busy" class="spin" :size="15" />就放在这里</button></div></div>
</ModalShell></template>
