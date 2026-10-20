export interface ModelConfig {
  provider: string; base_url: string; model: string; reasoning_effort: 'low'|'high'|'max'; temperature: number; max_tokens: number;
  max_steps: number; vision: boolean; tools: string[]; system_prompt: string;
}
export interface Provider { name: string; kind: string; base_url: string; model: string }
export interface Action { name: string; args: Record<string, unknown> }
export interface Project {
  session_id: string; name: string; idea: string; fingerprint: Record<string, unknown>;
  preview_entry: string | null; preview_ready: boolean; preview_url: string;
}
export interface Session {
  id: string; title: string; workspace: string; updated: string; archived: number;
  config: ModelConfig; pending: { action_requests: Action[] }[] | null; running?: boolean;
  project: Project | null; project_proposal: string | null; project_proposal_name: string | null;
}
export interface Attachment { name: string; path: string; size: number; image: boolean }
export interface Message { id: number; role: 'user' | 'assistant'; content: string; attachments: Attachment[]; created: string; kind: 'final'|'progress'; project_link: boolean }
export interface RunProgress { stage: string; detail: string; step: number; completed: string[]; elapsed_seconds: number; quiet_seconds: number }
export interface RunState { status: 'idle' | 'running' | 'done' | 'approval' | 'error' | 'stopped'; mode: 'chat'|'project'; text: string; error: string; progress?: RunProgress }
export interface RunEvent { id: number; kind: string; data: unknown; created: string }
export interface Snapshot { session: Session; messages: Message[]; run: RunState; events: RunEvent[] }
export interface Bootstrap { providers: Provider[]; config: ModelConfig; workspace: string; credentials: Record<string, boolean>; sessions: Session[] }
export interface FileEntry { name: string; path: string; directory: boolean; size: number }
export interface Memory { id: string; content: string; created: string }
export interface Directories { path: string; parent: string; roots: string[]; directories: { name: string; path: string }[] }
export interface Preview { text: string; image: string }
