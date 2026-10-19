<script setup lang="ts">
import { ref } from 'vue'
import { Check, CheckCircle2, Eye, EyeOff, LoaderCircle, Sparkles } from 'lucide-vue-next'
import ModalShell from './ModalShell.vue'
import { useDesk } from '../stores/desk'
import { api, body } from '../api/client'

const desk = useDesk()
const key = ref('')
const visible = ref(false)
const busy = ref(false)
const error = ref('')
const configured = () => !!desk.credentials.DeepSeek

async function connect() {
  if (busy.value || (!key.value.trim() && !configured())) return
  busy.value = true
  error.value = ''
  let temporaryKey = false
  try {
    if (key.value.trim()) { await desk.setKey('DeepSeek', key.value.trim(), false); temporaryKey = true }
    const config = desk.defaultConfig
    if (!config) throw new Error('默认配置尚未加载，请稍后重试')
    await api('/models/test', { method: 'POST', body: body(config) })
    if (key.value.trim()) await desk.setKey('DeepSeek', key.value.trim(), true)
    if (desk.session && !desk.locked) await desk.saveConfig({ ...config, tools: [...config.tools] })
    key.value = ''
    desk.dialog = null
  } catch (e) {
    if (temporaryKey) await desk.setKey('DeepSeek', '', false).catch(() => undefined)
    error.value = e instanceof Error ? e.message : '连接失败，请检查 API Key'
  } finally {
    busy.value = false
  }
}

async function clearKey() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { await desk.setKey('DeepSeek', ''); key.value = '' }
  catch (e) { error.value = e instanceof Error ? e.message : '清除失败' }
  finally { busy.value = false }
}
</script>

<template>
  <ModalShell title="模型配置" @close="desk.dialog=null">
    <form class="simple-model-settings" @submit.prevent="connect">
      <div class="fixed-model-card">
        <span class="fixed-model-icon"><Sparkles :size="21" /></span>
        <div><strong>DeepSeek V4.1 Flash</strong></div>
        <span v-if="configured()" class="configured"><CheckCircle2 :size="13" />已连接</span>
        <Check v-else :size="17" class="fixed-check" />
      </div>

      <label class="api-key-label" for="deepseek-key">API Key</label>
      <div class="password-field key-only-field">
        <input id="deepseek-key" v-model="key" :type="visible?'text':'password'" autocomplete="off"
          :disabled="busy" :required="!configured()"
          :placeholder="configured() ? '已配置，留空继续使用' : 'sk-…'" autofocus />
        <button type="button" class="icon-button" :aria-label="visible?'隐藏密钥':'显示密钥'" @click="visible=!visible">
          <EyeOff v-if="visible" :size="17" /><Eye v-else :size="17" />
        </button>
      </div>
      <div v-if="desk.locked" class="inline-notice">这次制作结束后，新设置就会生效。</div>
      <div v-if="error" role="alert" class="inline-error">{{ error }}</div>

      <div class="modal-actions simple-actions">
        <button v-if="configured()" type="button" class="text-button" :disabled="busy" @click="clearKey">清除密钥</button>
        <span v-else />
        <button class="primary connect-button" :disabled="busy || (!key.trim() && !configured())">
          <LoaderCircle v-if="busy" class="spin" :size="16" />
          {{ busy ? '正在连接…' : configured() && !key.trim() ? '完成' : '保存并连接' }}
        </button>
      </div>
    </form>
  </ModalShell>
</template>
