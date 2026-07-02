export type ApiResponse<T> = { success: boolean; message: string; data: T }

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  })
  const body = await response.json().catch(() => ({ message: `HTTP ${response.status}` }))
  if (!response.ok || body.success === false) throw new Error(body.message || body.detail || `HTTP ${response.status}`)
  return (body && typeof body === 'object' && 'data' in body ? (body as ApiResponse<T>).data : body) as T
}
