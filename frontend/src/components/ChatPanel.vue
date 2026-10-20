<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Check, CheckCircle2, ChevronRight, CircleHelp, Clock3, Copy, ExternalLink, Gamepad2, Image, Lightbulb, MessageCircle, ShieldCheck, Smile, Sparkles, User } from 'lucide-vue-next'
import { useDesk } from '../stores/desk'
import { api, body, sessionUrl } from '../api/client'
import MarkdownView from './MarkdownView.vue'
import AttachmentCard from './AttachmentCard.vue'
import MessageComposer from './MessageComposer.vue'
const desk = useDesk(), scroll = ref<HTMLElement>(), composer=ref<InstanceType<typeof MessageComposer>>()
const follow = ref(true), copied = ref<number | null>(null), choices = ref<string[]>([]), approving = ref(false)
const actions = computed(() => desk.session?.pending?.flatMap(p=>p.action_requests) ?? [])
const visibleMessages = computed(() => desk.state?.messages.filter(m=>m.kind!=='progress') ?? [])
const phases = ['理解想法','制作第一版','加入内容','检查作品','完成']
const progress = computed(() => desk.state?.run.progress)
const waitNote = computed(() => {
  const value=progress.value
  if(!value) return '每做好一步，这里都会更新。'
  if(value.quiet_seconds>=45) return '这一步比预计慢一些，我还在继续，没有停住。'
  if(value.elapsed_seconds>=12) return '还在认真制作，没有卡住。'
  return '每做好一步，这里都会更新。'
})
function elapsed(value=0){const minutes=Math.floor(value/60),seconds=value%60;return minutes?`${minutes}分${seconds}秒`:`${seconds}秒`}
watch(() => JSON.stringify(desk.session?.pending), () => { choices.value=actions.value.map(()=> 'approve') }, { immediate:true })
watch(() => [desk.state?.messages.length, desk.state?.run.text, actions.value.length], async () => { await nextTick(); if(follow.value && scroll.value) scroll.value.scrollTop=scroll.value.scrollHeight })
async function approve() {
  if(!desk.session || approving.value) return
  approving.value = true
  await desk.guard(() => api(sessionUrl(desk.session!.id,'resume'), {method:'POST',body:body({decisions: choices.value.map(type=>({type}))})}))
  approving.value = false
}
function onScroll() { const el=scroll.value; if(el) follow.value=el.scrollHeight-el.scrollTop-el.clientHeight < 100 }
async function copy(id:number, text:string) { await desk.guard(async()=>{ await navigator.clipboard.writeText(text); copied.value=id; setTimeout(()=>copied.value=null,1800) }) }
function startProject(){const idea=desk.session?.project_proposal;if(!idea)return;desk.projectDraft=idea;desk.projectNameDraft=desk.session?.project_proposal_name || '';desk.dialog='new-project'}
function dismissProject(){void desk.guard(()=>desk.dismissProjectProposal())}
</script>
<template>
  <section class="chat-panel">
    <div ref="scroll" class="conversation-scroll" @scroll="onScroll">
      <div v-if="!visibleMessages.length" class="welcome">
        <template v-if="desk.session?.project"><div class="welcome-kicker"><span class="welcome-symbol"><img src="/brand-dolphin.png" alt="" /></span><span>你的点子已经准备好了</span></div>
          <h1>一起把想法<br />变成真的吧！</h1><p>下面已经放好了你刚才说的想法。<br class="desktop-only" />点一下箭头，我就开始做第一版。</p>
          <div class="suggestion-grid"><button @click="composer?.setText('我想先做出一个马上能玩的小游戏。')"><Gamepad2 :size="20" /><strong>做个小游戏</strong><span>先做出能玩的第一版</span><ChevronRight :size="16" /></button><button @click="composer?.setText('我有一张图片，想用它做一个有趣的作品。')"><Image :size="20" /><strong>用图片创作</strong><span>可以把图片放到下面</span><ChevronRight :size="16" /></button><button @click="composer?.setText('我只有一个模糊的点子，请直接帮我做出第一版。')"><Lightbulb :size="20" /><strong>从点子开始</strong><span>不完整也没有关系</span><ChevronRight :size="16" /></button></div>
        </template>
        <template v-else><div class="welcome-kicker"><span class="welcome-symbol"><img src="/brand-dolphin.png" alt="" /></span><span>想说什么都可以</span></div>
          <h1>先聊一聊吧！</h1><p>可以打招呼、问问题，也可以告诉我一个刚想到的点子。<br class="desktop-only" />如果要把它做成作品，我会先问问你。</p>
          <div class="suggestion-grid"><button @click="composer?.setText('你好呀！')"><Smile :size="20" /><strong>打个招呼</strong><span>先认识一下</span><ChevronRight :size="16" /></button><button @click="composer?.setText('我有一个问题想问你。')"><CircleHelp :size="20" /><strong>问个问题</strong><span>不懂的都可以问</span><ChevronRight :size="16" /></button><button @click="composer?.setText('我有一个刚想到的点子。')"><MessageCircle :size="20" /><strong>说个想法</strong><span>先聊聊，不会直接开工</span><ChevronRight :size="16" /></button></div>
        </template>
      </div>
      <div v-else class="message-list">
        <article v-for="m in visibleMessages" :key="m.id" class="message" :class="m.role">
          <div class="message-avatar"><User v-if="m.role==='user'" :size="17" /><img v-else src="/brand-dolphin.png" alt="创作伙伴" /></div>
          <div class="message-body"><div class="message-meta"><strong>{{ m.role==='user' ? '你' : '创作伙伴' }}</strong><time>{{ new Date(m.created).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}) }}</time><button class="icon-button copy-message" :aria-label="`复制消息 ${m.id}`" @click="copy(m.id,m.content)"><Check v-if="copied===m.id" :size="14" /><Copy v-else :size="14" /></button></div><MarkdownView :text="m.content" /><a v-if="m.role==='assistant' && m.kind==='final' && m.project_link && desk.session?.project?.preview_ready" class="message-project-link" :href="desk.session.project.preview_url" target="_blank"><ExternalLink :size="15" />打开我的作品</a><div v-if="m.attachments.length" class="message-attachments"><AttachmentCard v-for="a in m.attachments" :key="a.path" :item="a" :sid="desk.session!.id" /></div></div>
        </article>
        <div v-if="desk.running && !desk.session?.project" class="chat-replying" role="status" aria-live="polite"><span class="message-avatar"><img src="/brand-dolphin.png" alt="" /></span><span>正在回复</span><div class="thinking"><i /><i /><i /></div></div>
        <section v-if="desk.running && desk.session?.project" class="making-progress" role="status" aria-live="polite">
          <div class="progress-heading"><span class="progress-spark"><Sparkles :size="19" class="pulse" /></span><div><small>正在制作</small><h3>{{ progress?.stage || '正在理解你的想法' }}</h3></div><span class="elapsed"><Clock3 :size="13" />{{ elapsed(progress?.elapsed_seconds) }}</span></div>
          <p class="progress-detail">{{ progress?.detail || '我先找出这个作品最重要、最好玩的部分。' }}</p>
          <div class="phase-track"><div v-for="(phase,index) in phases" :key="phase" :class="{done:index<(progress?.step??0),active:index===(progress?.step??0)}"><i><Check v-if="index<(progress?.step??0)" :size="11" /></i><span>{{ phase }}</span></div></div>
          <div v-if="progress?.completed.length" class="completed-list"><span v-for="item in progress.completed" :key="item"><CheckCircle2 :size="13" />{{ item }}</span></div>
          <p class="patience-note">{{ waitNote }}</p>
        </section>
        <section v-if="!desk.running && !desk.session?.project && desk.session?.project_proposal" class="project-proposal"><span class="proposal-icon"><Sparkles :size="20" /></span><div><small>想把它做出来吗？</small><h3>现在开始做“{{ desk.session.project_proposal_name || '这个作品' }}”吗？</h3><p>{{ desk.session.project_proposal }}</p><div class="proposal-actions"><button class="primary" @click="startProject">开始做</button><button class="secondary" @click="dismissProject">先聊一聊</button></div></div></section>
        <div v-if="desk.state?.run.status==='error'" class="inline-error">这一步没有完成。请检查网络，或者再发一次刚才的话。<small>你的作品和已经完成的内容都还在。</small></div>
        <div v-if="desk.state?.run.status==='stopped'" class="inline-notice">已经停下来了，之前做好的内容都会保留。</div>
        <div v-if="actions.length && !desk.running" class="approval-box"><h3><ShieldCheck :size="19" />需要你点一下</h3><p>为了继续制作，我需要在这台电脑上准备并运行作品。如果不确定，可以请家长来看。</p><div v-for="(action,i) in actions" :key="i" class="approval-action"><div class="simple-choice"><label :for="`decision-${i}`">你愿意继续吗？</label><select :id="`decision-${i}`" v-model="choices[i]"><option value="approve">继续制作</option><option value="reject">先不要</option></select></div><details class="parent-details"><summary>给家长查看详细内容</summary><pre>{{ action.name }}\n{{ JSON.stringify(action.args,null,2) }}</pre></details></div><button class="primary" :disabled="approving || !desk.ready" @click="approve">{{ approving ? '正在继续…' : '确定' }}</button><button v-if="!desk.ready" class="text-button" @click="desk.dialog='settings'">请先进行模型配置</button></div>
      </div>
    </div>
    <MessageComposer ref="composer" :key="desk.session?.id" />
  </section>
</template>
