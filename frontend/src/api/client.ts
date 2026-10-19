export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: `请求失败 (${response.status})` }))
    const message = typeof data.detail === 'string' ? data.detail : '输入格式不正确，请检查填写内容'
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
export const body = (value: unknown) => JSON.stringify(value)
export const sessionUrl = (id: string, endpoint: string) => `/sessions/${encodeURIComponent(id)}/${endpoint}`
export const fileUrl = (id: string, path: string) => `/api${sessionUrl(id, 'download')}?path=${encodeURIComponent(path)}`
