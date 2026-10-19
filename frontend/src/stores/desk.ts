import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { api, body, sessionUrl } from '../api/client'
import type { Attachment, Bootstrap, ModelConfig, Provider, Session, Snapshot } from '../types'

export const useDesk = defineStore('desk', () => {
  const sessions = ref<Session[]>([])
  const providers = ref<Provider[]>([])
  const defaultConfig = ref<ModelConfig | null>(null)
  const credentials = ref<Record<string, boolean>>({})
  const workspace = ref('')
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
  let source: EventSource | null = null
  let selection = 0
  const session = computed(() => state.value?.session)
  const running = computed(() => state.value?.run.status === 'running')
  const locked = computed(() => running.value || !!session.value?.pending)
  const ready = computed(() => !!credentials.value[session.value?.config.provider ?? ''])

  async function guard<T>(fn: () => Promise<T>): Promise<T | undefined> {
    error.value = ''
    try { return await fn() } catch (e) { error.value = e instanceof Error ? e.message : '操作失败'; return undefined }
  }
  async function initialize() {
    loading.value = true
    try {
      const result = await api<Bootstrap>('/bootstrap')
      sessions.value = result.sessions; providers.value = result.providers; defaultConfig.value = result.config
      credentials.value = result.credentials; workspace.value = result.workspace
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
  async function createProject(idea: string, placement: 'auto'|'manual' = 'auto', workspacePath?: string) {
    const value = await api<Session>('/sessions', { method: 'POST', body: body({ idea, placement, workspace: workspacePath }) })
    workspace.value = value.workspace; archived.value = false
    await refreshSessions()
    return value.id
  }
  async function send(text: string, attachments: Attachment[]) {
    if (!session.value || sending.value) return false
    const id = session.value.id
    sending.value = true
    try {
      await api(sessionUrl(id, 'messages'), { method: 'POST', body: body({ text, attachments: attachments.map(a => a.path) }) })
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
  function dispose() { selection++; source?.close(); source = null }
  return { sessions, providers, credentials, workspace, state, loading, connected, sending, error, dialog,
    sidebarOpen, inspectorOpen, archived, refreshFiles, defaultConfig, session, running, locked, ready,
    guard, initialize, refreshSessions, select, createProject, send, saveConfig, setKey, dispose }
})
