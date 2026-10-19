<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Brain, Download, File, Folder, FolderOpen, LoaderCircle, RefreshCw, Terminal, Trash2, Upload, X } from 'lucide-vue-next'
import { useDesk } from '../stores/desk'
import { api, body, fileUrl, sessionUrl } from '../api/client'
import type { Attachment, FileEntry, Memory, Preview } from '../types'
const desk=useDesk(), tab=ref('files'), path=ref('.'), files=ref<FileEntry[]>([]), memories=ref<Memory[]>([]), note=ref(''), preview=ref<(Preview & {path:string;name:string}) | null>(null), busy=ref(false), picker=ref<HTMLInputElement>()
let generation=0
const name = computed(()=>desk.session?.workspace.split(/[/\\]/).filter(Boolean).pop())
const labels: Record<string,string> = {tool_call:'动手制作',tool_result:'完成一步',approval:'等你确认',run:'开始制作',error:'遇到问题',stopped:'已经停下',usage:'认真思考',plan:'制作计划'}
const plan = computed(()=>desk.state?.events.find(e=>e.kind==='plan')?.data as string[] | undefined)
async function load() {
  if(!desk.session) return
  const id=desk.session.id, version=++generation
  busy.value=true
  await desk.guard(async()=>{
    const [f,m]=await Promise.all([api<FileEntry[]>(`${sessionUrl(id,'files')}?path=${encodeURIComponent(path.value)}`),api<Memory[]>(sessionUrl(id,'memories'))])
    if(version===generation) {files.value=f;memories.value=m}
  })
  if(version===generation) busy.value=false
}
watch(()=>desk.session?.id,()=>{path.value='.';preview.value=null;note.value=''; void load()}, {immediate:true})
watch(()=>desk.refreshFiles,()=>{void load()})
function navigate(dir:string) {path.value=dir;preview.value=null; void load()}
function parent() {const parts=path.value.replaceAll('\\','/').split('/');parts.pop();navigate(parts.join('/')||'.')}
function open(item:FileEntry) {
  if(item.directory) {navigate(item.path);return}
  const id=desk.session!.id
  desk.guard(async()=>{const result=await api<Preview>(`${sessionUrl(id,'preview')}?path=${encodeURIComponent(item.path)}`); if(desk.session?.id===id) preview.value={...result,path:item.path,name:item.name}})
}
function addMemory() {desk.guard(async()=>{await api(sessionUrl(desk.session!.id,'memories'),{method:'POST',body:body({content:note.value})});note.value='';await load()})}
function forget(id:string) {desk.guard(async()=>{await api(sessionUrl(desk.session!.id,`memories/${id}`),{method:'DELETE'});await load()})}
async function upload(files:FileList) {
  if(files.length>8 || Array.from(files).some(f=>f.size>20*1024*1024)) {desk.error='最多上传 8 个文件，每个不超过 20 MB';return}
  const id=desk.session!.id, data=new FormData();Array.from(files).forEach(f=>data.append('files',f))
  await desk.guard(async()=>{await api<Attachment[]>(sessionUrl(id,'uploads'),{method:'POST',body:data});await load()})
  if(picker.value) picker.value.value=''
}
function eventName(data:unknown) { return data && typeof data==='object' && 'name' in data ? String(data.name ?? '') : '' }
</script>
<template>
  <aside class="inspector" :class="{ open:desk.inspectorOpen }">
    <div class="inspector-heading"><h3>作品内容</h3><button class="icon-button" aria-label="收起作品内容" @click="desk.inspectorOpen=false"><X :size="17" /></button></div>
    <div class="workspace-card"><span><FolderOpen :size="21" /></span><div><strong>{{ name }}</strong></div></div>
    <div class="tabs" role="tablist" aria-label="作品内容"><button :class="{active:tab==='files'}" role="tab" :aria-selected="tab==='files'" @click="tab='files'"><Folder :size="15" />内容</button><button :class="{active:tab==='memory'}" role="tab" :aria-selected="tab==='memory'" @click="tab='memory';load()"><Brain :size="15" />喜好</button><button :class="{active:tab==='activity'}" role="tab" :aria-selected="tab==='activity'" @click="tab='activity'"><Terminal :size="15" />过程</button></div>
    <div class="inspector-content">
      <template v-if="tab==='files'"><div class="file-toolbar"><button v-if="path!=='.'" class="icon-button" aria-label="返回上一级" @click="parent"><ArrowLeft :size="15" /></button><span>{{ path==='.' ? '作品里的内容' : path }}</span><button class="icon-button" aria-label="重新看看" @click="load"><RefreshCw :size="14" :class="{spin:busy}" /></button></div>
        <div v-if="!files.length" class="inspector-empty"><FolderOpen :size="32" :stroke-width="1.2" /><strong>这里还空空的</strong><p>开始制作后，作品内容会出现在这里。</p></div>
        <button v-for="f in files" :key="f.path" class="file-row" @click="open(f)"><Folder v-if="f.directory" :size="17" /><File v-else :size="17" /><span>{{ f.name }}</span><small v-if="!f.directory">{{ (f.size/1024).toFixed(0) }} K</small></button>
        <button class="upload-zone" @click="picker?.click()"><Upload :size="19" /><strong>放入图片或文件</strong><small>可以一次放入多个</small></button><input ref="picker" type="file" multiple hidden @change="e=>{const f=(e.target as HTMLInputElement).files;if(f)upload(f)}" />
        <div v-if="preview" class="file-preview"><div><strong>{{ preview.name }}</strong><button class="icon-button" aria-label="关闭预览" @click="preview=null"><X :size="15" /></button></div><img v-if="preview.image" :src="preview.image" :alt="preview.name" /><pre v-else>{{ preview.text }}</pre><a class="secondary" :href="fileUrl(desk.session!.id,preview.path)" download><Download :size="14" />下载文件</a></div>
      </template>
      <template v-else-if="tab==='memory'"><div class="panel-intro"><h4>记住你喜欢的样子</h4><p>比如“我喜欢蓝色”和“人物要可爱”。</p></div><form @submit.prevent="addMemory"><textarea v-model="note" placeholder="写下一条你的喜好…" aria-label="添加喜好" maxlength="4000" /><button class="primary full" :disabled="!note.trim()">记住它</button></form><div class="section-label">已经记住 {{ memories.length }} 条</div><div v-for="m in memories" :key="m.id" class="memory-card"><p>{{ m.content }}</p><button class="icon-button" :aria-label="`忘掉 ${m.content}`" @click="forget(m.id)"><Trash2 :size="14" /></button></div></template>
      <template v-else><div class="panel-intro"><h4>看看做到哪一步了</h4></div><div v-if="plan" class="plan-card"><strong>现在的计划</strong><p v-for="step in plan" :key="step">{{ step }}</p></div><p v-if="!desk.state?.events.length" class="empty-small">开始制作后，过程会显示在这里。</p><div v-for="event in desk.state?.events.filter(e=>['run','plan','tool_call','tool_result','approval','stopped','error'].includes(e.kind))" :key="event.id" class="event-card friendly-event"><div><span class="event-marker" :class="event.kind" />{{ labels[event.kind] ?? '完成一步' }}</div><time>{{ new Date(event.created).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) }}</time></div></template>
      <LoaderCircle v-if="busy" :size="16" class="spin muted" />
    </div>
  </aside>
</template>
