import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, body, sessionUrl } from '../api/client'
import type { Attachment, Bootstrap, DemoStatus, ModelConfig, Provider, Session, Snapshot } from '../types'

export const useDesk = defineStore('desk', () => {
  const sessions = ref<Session[]>([])
  const providers = ref<Provider[]>([])
  const defaultConfig = ref<ModelConfig | null>(null)
  const credentials = ref<Record<string, boolean>>({})
  const workspace = ref('')
  const defaultWorkspace = ref('')
  const state = ref<Snapshot | null>(null)
  const loading = ref(true)
  const connected = ref(false)
  const sending = ref(false)
  const error = ref('')
  const dialog = ref<'settings' | 'new-project' | 'session' | null>(null)
  const sidebarOpen = ref(false)
  const inspectorOpen = ref(window.innerWidth >= 1000)
  const archived = ref(false)
  const refreshFiles = ref(0)
  const projectDraft = ref('')
  const projectNameDraft = ref('')
  const demo = ref<DemoStatus>({ enabled: false, limit: 0, remaining: 0, expires_at: 0 })
  const demoNow = ref(Date.now() / 1000)
  let source: EventSource | null = null
  let clock: number | null = null
  let selection = 0
  const session = computed(() => state.value?.session)
  const running = computed(() => state.value?.run.status === 'running')
  const locked = computed(() => running.value || !!session.value?.pending)
  const ready = computed(() => !!credentials.value[session.value?.config.provider ?? ''])
  const demoSeconds = computed(() => demo.value.enabled ? Math.max(0, Math.ceil(demo.value.expires_at - demoNow.value)) : 0)
  const canSend = computed(() => !demo.value.enabled || (demo.value.remaining > 0 && demoSeconds.value > 0))

  async function guard<T>(fn: () => Promise<T>): Promise<T | undefined> {
    error.value = ''
    try { return await fn() } catch (e) { error.value = e instanceof Error ? e.message : '操作失败'; return undefined }
  }
  async function initialize() {
    loading.value = true
    try {
      const result = await api<Bootstrap>('/bootstrap')
      sessions.value = result.sessions; providers.value = result.providers; defaultConfig.value = result.config
      credentials.value = result.credentials; workspace.value = result.workspace; defaultWorkspace.value = result.workspace
      demo.value = result.demo
      if (demo.value.enabled && clock === null) clock = window.setInterval(() => { demoNow.value = Date.now() / 1000 }, 1000)
    } finally { loading.value = false }
  }
  async function refreshSessions() { sessions.value = await api<Session[]>(`/sessions?archived=${archived.value}`) }
  function applySnapshot(value: Snapshot) {
    const oldStatus = state.value?.run.status
    state.value = value
    workspace.value = value.session.workspace
    const index = sessions.value.findIndex(s => s.id === value.session.id)
    if (index >= 0) sessions.value[index] = { ...value.session, running: value.run.status === 'running' }
    if (oldStatus === 'running' && value.run.status !== 'running') refreshFiles.value++
  }
  async function select(id: string) {
    const version = ++selection
    source?.close(); source = null; connected.value = false; state.value = null
    const snapshot = await api<Snapshot>(`/sessions/${id}`)
    if (version !== selection) return
    applySnapshot(snapshot)
    source = new EventSource(`/api${sessionUrl(id, 'stream')}`)
    source.addEventListener('state', (event) => {
      if (version !== selection) return
      connected.value = true
      applySnapshot(JSON.parse((event as MessageEvent).data) as Snapshot)
    })
    source.onopen = () => { if (version === selection) connected.value = true }
    source.onerror = () => { if (version === selection) connected.value = false }
    sidebarOpen.value = false
  }
  async function createProject(idea: string, name: string, placement: 'auto'|'manual' = 'auto', workspacePath?: string) {
    const value = await api<Session>('/sessions', { method: 'POST', body: body({ kind: 'project', idea, name, placement, workspace: workspacePath }) })
    workspace.value = value.workspace; archived.value = false
    await refreshSessions()
    return value.id
  }
  async function createChat() {
    const value = await api<Session>('/sessions', { method: 'POST', body: body({ kind: 'chat' }) })
    workspace.value = value.workspace; archived.value = false
    await refreshSessions()
    return value.id
  }
  async function attachProject(idea: string, name: string, placement: 'auto'|'manual' = 'auto', workspacePath?: string) {
    if (!session.value) throw new Error('请先打开一个对话')
    const id = session.value.id
    await api<Session>(sessionUrl(id, 'project'), { method: 'POST', body: body({ idea, name, placement, workspace: workspacePath }) })
    projectDraft.value = ''
    projectNameDraft.value = ''
    await refreshSessions()
    await select(id)
    return id
  }
  async function dismissProjectProposal() {
    if (!session.value) return
    const id = session.value.id
    await api<Session>(sessionUrl(id, 'project-proposal'), { method: 'DELETE' })
    const snapshot = await api<Snapshot>(`/sessions/${id}`)
    if (session.value?.id === id) applySnapshot(snapshot)
  }
  async function send(text: string, attachments: Attachment[]) {
    if (!session.value || sending.value) return false
    const id = session.value.id
    sending.value = true
    try {
      const result = await api<{status:string;demo:DemoStatus}>(sessionUrl(id, 'messages'), { method: 'POST', body: body({ text, attachments: attachments.map(a => a.path) }) })
      if (result.demo.enabled) demo.value = result.demo
      const snapshot = await api<Snapshot>(`/sessions/${id}`)
      if (session.value?.id === id) applySnapshot(snapshot)
      return true
    } finally { sending.value = false }
  }
  async function saveConfig(config: ModelConfig) {
    if (!session.value) return
    const id = session.value.id
    await api(sessionUrl(id, 'config'), { method: 'PUT', body: body(config) })
    const snapshot = await api<Snapshot>(`/sessions/${id}`)
    if (session.value?.id === id) applySnapshot(snapshot)
  }
  async function setKey(provider: string, apiKey: string, persistent = true) {
    credentials.value = await api<Record<string, boolean>>('/credentials', { method: 'PUT', body: body({ provider, api_key: apiKey, persistent }) })
  }
  function dispose() { selection++; source?.close(); source = null; if(clock!==null){window.clearInterval(clock);clock=null} }
  return { sessions, providers, credentials, workspace, defaultWorkspace, state, loading, connected, sending, error, dialog,
    sidebarOpen, inspectorOpen, archived, refreshFiles, projectDraft, projectNameDraft, defaultConfig, demo, demoSeconds, canSend, session, running, locked, ready,
    guard, initialize, refreshSessions, select, createProject, createChat, attachProject, dismissProjectProposal,
    send, saveConfig, setKey, dispose }
})
