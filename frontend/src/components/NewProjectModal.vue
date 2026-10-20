<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowUp, ChevronRight, Folder, FolderHeart, HardDrive, LoaderCircle, MessageCircle, Sparkles } from 'lucide-vue-next'
import ModalShell from './ModalShell.vue'
import { useDesk } from '../stores/desk'
import { api } from '../api/client'
import type { Directories } from '../types'

type Step = 'choice'|'idea'|'placement'|'directory'
const desk=useDesk(), router=useRouter()
const converting=Boolean(desk.projectDraft && desk.session && !desk.session.project)
const step=ref<Step>(converting?(desk.demo.enabled?'idea':'placement'):'choice')
const idea=ref(desk.projectDraft), path=ref(desk.defaultWorkspace || desk.workspace)
const projectName=ref(converting?desk.projectNameDraft:''), namedIdea=ref(projectName.value?idea.value.trim():'')
const listing=ref<Directories>(), busy=ref(false), error=ref('')
const title=computed(()=>converting?'开始制作这个想法':'开始新的对话')
const subtitle=computed(()=>{
  if(step.value==='choice') return '可以先聊一聊，也可以直接开始做作品。'
  if(step.value==='idea') return '先说说你想做什么，剩下的交给我。'
  if(step.value==='placement') return '选择作品放在哪里。推荐让我自动准备。'
  return '选择一个你熟悉的文件夹。'
})
function close(){desk.projectDraft='';desk.projectNameDraft='';desk.dialog=null}
async function focusIdea(){await nextTick();document.getElementById('project-idea')?.focus()}
function chooseProject(){step.value='idea';void focusIdea()}
async function suggestName(){
  const value=idea.value.trim()
  if(!value)return false
  if(projectName.value && namedIdea.value===value)return true
  busy.value=true;error.value=''
  try{const result=await api<{name:string}>('/project-name',{method:'POST',body:JSON.stringify({idea:value})});projectName.value=result.name;namedIdea.value=value;return true}
  catch(e){error.value=e instanceof Error?e.message:'暂时没有想好名字，再试一次吧';return false}
  finally{busy.value=false}
}
async function next(){if(await suggestName()){if(desk.demo.enabled)await create('auto');else step.value='placement'}}
async function browse(value=path.value){busy.value=true;error.value='';try{listing.value=await api<Directories>(`/directories?path=${encodeURIComponent(value)}`);path.value=listing.value.path}catch(e){error.value=e instanceof Error?e.message:'这里暂时打不开'}finally{busy.value=false}}
async function createChat(){busy.value=true;error.value='';try{const id=await desk.createChat();close();await router.push(`/chat/${id}`)}catch(e){error.value=e instanceof Error?e.message:'对话没有打开，再试一次吧'}finally{busy.value=false}}
async function create(placement:'auto'|'manual') {
  if(!await suggestName())return
  busy.value=true;error.value=''
  try{
    const id=converting
      ? await desk.attachProject(idea.value,projectName.value,placement,placement==='manual'?path.value:undefined)
      : await desk.createProject(idea.value,projectName.value,placement,placement==='manual'?path.value:undefined)
    close();await router.push(`/chat/${id}`)
    if(converting) await desk.guard(()=>desk.send('开始制作吧',[]))
  }catch(e){error.value=e instanceof Error?e.message:'作品没有准备好，再试一次吧'}finally{busy.value=false}
}
function manual(){step.value='directory';void browse()}
onMounted(()=>{if(step.value==='idea') void focusIdea();if(converting&&desk.demo.enabled)void create('auto');else if(converting&&!projectName.value)void suggestName()})
</script>

<template><ModalShell :title="title" :subtitle="subtitle" @close="close">
  <div v-if="step==='choice'" class="placement-grid start-choice-grid">
    <button class="placement-card" :disabled="busy" @click="createChat"><span><MessageCircle :size="25" /></span><strong>先聊一聊</strong><p>打个招呼、问问题，或者随便说说话。</p><ChevronRight :size="18" /></button>
    <button class="placement-card recommended" :disabled="busy" @click="chooseProject"><span><Sparkles :size="25" /></span><strong>做一个作品</strong><p>把一个想法做成能看到、能玩或能使用的东西。</p><ChevronRight :size="18" /></button>
    <div v-if="busy" class="creating-note"><LoaderCircle class="spin" :size="17" />正在打开新对话…</div><div v-if="error" class="inline-error">{{ error }}</div>
  </div>
  <form v-else-if="step==='idea'" class="idea-step" @submit.prevent="next"><label for="project-idea">今天你想做什么？</label><textarea id="project-idea" v-model="idea" maxlength="4000" placeholder="比如：我想做一个双人坦克游戏，两个人都能移动和放技能！" /><p>不用想得很完整，想到什么就说什么。</p><div class="modal-actions"><button v-if="!converting" class="secondary" type="button" @click="step='choice'"><ArrowLeft :size="15" />返回</button><span v-else /><button class="primary" :disabled="!idea.trim()">下一步 <ChevronRight :size="16" /></button></div></form>
  <div v-else-if="step==='placement'"><div class="idea-summary"><small>作品名字</small><strong>{{ projectName || '正在想一个好记的名字…' }}</strong><p v-if="converting">{{ idea }}</p></div><div class="placement-grid"><button class="placement-card recommended" :disabled="busy" @click="create('auto')"><span><Sparkles :size="25" /></span><strong>帮我准备好 <i>推荐</i></strong><p>我会新建同名作品文件夹，马上开始制作。</p><ChevronRight :size="18" /></button><button class="placement-card" :disabled="busy" @click="manual"><span><FolderHeart :size="25" /></span><strong>我自己选择位置</strong><p>选好存放位置后，我会在里面新建作品文件夹。</p><ChevronRight :size="18" /></button></div><div v-if="busy" class="creating-note"><LoaderCircle class="spin" :size="17" />正在给作品取名字…</div><div v-if="error" class="inline-error">{{ error }}</div><div class="modal-actions"><button class="secondary" @click="step='idea';focusIdea()"><ArrowLeft :size="15" />返回修改想法</button></div></div>
  <div v-else><form class="path-form" @submit.prevent="browse()"><label for="project-path">你选择的位置</label><div><input id="project-path" v-model="path" /><button class="secondary" :disabled="busy">打开</button></div></form><p class="folder-create-note">我会在这里新建“{{ projectName }}”文件夹，不会改动原来的文件。</p><div class="directory-controls"><button class="text-button" :disabled="busy || !listing || listing.path===listing.parent" @click="browse(listing?.parent)"><ArrowUp :size="15" />上一级</button><button v-for="root in listing?.roots" :key="root" class="text-button" :disabled="busy" @click="browse(root)"><HardDrive :size="14" />{{ root }}</button></div><div class="directory-list"><button v-for="dir in listing?.directories" :key="dir.path" :disabled="busy" @click="browse(dir.path)"><Folder :size="19" /><span>{{ dir.name }}</span><ChevronRight :size="16" /></button><p v-if="!listing?.directories.length" class="empty-small">这里没有别的文件夹，可以直接选择这里。</p></div><div v-if="error" class="inline-error">{{ error }}</div><div class="modal-actions"><button class="secondary" @click="step='placement'"><ArrowLeft :size="15" />返回</button><button class="primary" :disabled="busy" @click="create('manual')"><LoaderCircle v-if="busy" class="spin" :size="15" />就放在这里</button></div></div>
</ModalShell></template>
