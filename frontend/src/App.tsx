import { FormEvent, useCallback, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from './api'

type Check = { status: string; message: string; database_name?: string; database_url?: string }
type Config = {
  notion: { configured: boolean; token_saved: boolean; token_length: number; database_id: string; check: Check }
}
type XhsSession = { status: string; loggedIn: boolean; cookieValid: boolean; account: { id: string; nickname: string; avatarUrl: string }; loginTime: string | null; updatedAt: string; expireAt: string | null; remainingSeconds: number | null }
type InboxItem = { item_id: string; content: string; urls: string[]; status: 'pending' | 'failed'; failure_reason: string }
type Inbox = { version: string; raw_content: string; pending_item_count: number; pending_url_count: number; items: InboxItem[] }
type Task = { task_id: string | null; status: 'idle' | 'processing' | 'success' | 'failed'; current_url: string; processed: number; success: number; skipped_duplicate: number; failed: number; last_error: string }
type XhsTask = { task_id: string | null; status: 'idle' | 'fetching' | 'processing' | 'cancelling' | 'cancelled' | 'success' | 'failed'; phase: string; step: string; message: string; requested: number; fetched: number; discovered: number; processed: number; success: number; failed: number; current_index: number; current_title: string; page_url: string; last_error: string; started_at: string | null; updated_at: string | null; last_progress_at: string | null; heartbeat_at: string | null; finished_at: string | null }
type RecentItem = { item_id: string; title: string; original_url: string; normalized_url: string; notion_url: string; created_at: string; status: string }
type MediaCandidate = { item_id: string; title: string; media_fetch_status: string; media_provider: string; ocr_status: string; transcription_status: string; content_completeness: string; updated_at: string }

const emptyConfig: Config = {
  notion: { configured: false, token_saved: false, token_length: 0, database_id: '', check: { status: 'unknown', message: '尚未检测' } },
}
const emptyInbox: Inbox = { version: '', raw_content: '', pending_item_count: 0, pending_url_count: 0, items: [] }
const emptyTask: Task = { task_id: null, status: 'idle', current_url: '', processed: 0, success: 0, skipped_duplicate: 0, failed: 0, last_error: '' }

function Card({ title, action, children, className = '' }: { title: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <section className={`card ${className}`}><div className="card-head"><h2>{title}</h2>{action}</div>{children}</section>
}

function Badge({ status, children }: { status: string; children: React.ReactNode }) {
  const tone = status === 'success' || status === 'configured' || status === 'archived' ? 'good' : status === 'failed' || status.includes('expire') ? 'bad' : status === 'processing' ? 'busy' : 'muted'
  return <span className={`badge ${tone}`}>{children}</span>
}

function FavoriteSyncPanel({ enabled }: { enabled: boolean }) {
  const [limitText, setLimitText] = useState('20')
  const [syncing, setSyncing] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [task, setTask] = useState<XhsTask | null>(null)
  const active = task?.status === 'fetching' || task?.status === 'processing' || task?.status === 'cancelling'
  const progress = task?.status === 'processing' && task.fetched ? Math.round(task.processed / task.fetched * 100) : 0
  const elapsed = task?.started_at ? Math.max(0, Math.floor((Date.now() - new Date(task.started_at).getTime()) / 1000)) : 0
  const progressAge = task?.last_progress_at ? Math.max(0, Math.floor((Date.now() - new Date(task.last_progress_at).getTime()) / 1000)) : 0
  const heartbeatAge = task?.heartbeat_at ? Math.max(0, Math.floor((Date.now() - new Date(task.heartbeat_at).getTime()) / 1000)) : null
  const updateTask = useCallback((value: XhsTask) => {
    setTask(value)
    if (value.status === 'success') { setResult(`已完成：成功整理 ${value.success} 条收藏`); setError('') }
    if (value.status === 'failed') setError(value.last_error || `任务结束，其中 ${value.failed} 条处理失败`)
    if (value.status === 'cancelled') { setResult('任务已取消'); setError('') }
  }, [])
  useEffect(() => { void api<XhsTask>('/api/xhs/sync/status').then(updateTask).catch(() => undefined) }, [updateTask])
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => {
      void api<XhsTask>('/api/xhs/sync/status').then(updateTask).catch(value => setError(`状态刷新失败：${value.message}`))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [active, updateTask])
  const run = () => {
    const limit = Math.max(1, Math.min(100, Number(limitText) || 1))
    setLimitText(String(limit)); setSyncing(true); setResult(null); setError('')
    api<XhsTask>('/api/xhs/sync', { method: 'POST', body: JSON.stringify({ limit }) })
      .then(updateTask)
      .catch(value => setError(value.message))
      .finally(() => setSyncing(false))
  }
  const cancel = () => api<XhsTask>('/api/xhs/sync/cancel', { method: 'POST' }).then(updateTask).catch(value => setError(value.message))
  const stepLabels: Record<string, string> = { connecting: '连接 Chrome', opening_page: '创建标签页', opening_browser: '启动浏览器', opening_home: '打开小红书首页', locating_profile: '查找个人主页', opening_profile: '进入个人主页', opening_favorites: '打开收藏标签', locating_items: '识别收藏卡片', reading_item: '读取收藏详情', opening_detail: '打开收藏详情', fetching_media: '下载视频', opencli_download: 'OpenCLI 降级下载', video_ocr: '识别画面文字', audio_transcription: 'Whisper 语音转录', assembling_content: '合并视频内容', ai_analysis: 'AI 分析', notion_sync: '同步 Notion' }
  const statusLabel = task?.status === 'fetching' ? (stepLabels[task.step] || '读取收藏列表') : task?.status === 'processing' ? 'AI 分析并同步 Notion' : task?.status === 'cancelling' ? '正在取消' : task?.status === 'cancelled' ? '已取消' : task?.status === 'success' ? '任务完成' : task?.status === 'failed' ? '任务失败' : '等待开始'
  return <Card title="读取收藏" action={<Badge status={active ? 'processing' : enabled ? 'configured' : 'unknown'}>{active ? statusLabel : enabled ? '可读取' : '未连接 Chrome'}</Badge>}>
    <div className="sync-panel home-sync">
      <label>本次读取数量（1–100）<input type="number" min={1} max={100} value={limitText} disabled={active} onChange={event => setLimitText(event.target.value)} /></label>
      {task?.task_id && <section className="xhs-progress" aria-live="polite">
        <div className="xhs-steps"><span className={task.status !== 'idle' ? 'active' : ''}>1 读取</span><span className={task.status === 'processing' || task.status === 'success' || task.status === 'failed' ? 'active' : ''}>2 分析与同步</span><span className={task.status === 'success' || task.status === 'failed' ? 'active' : ''}>3 完成</span></div>
        <div className={`progress-track ${task.status === 'fetching' ? 'indeterminate' : ''}`} role="progressbar" aria-label="收藏任务进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={task.status === 'fetching' ? undefined : progress}><span style={{ width: task.status === 'fetching' ? '35%' : `${progress}%` }} /></div>
        <div className="xhs-progress-head"><strong>{statusLabel}</strong><span>{task.status === 'fetching' ? `目标 ${task.requested} 条` : `${task.processed}/${task.fetched} 条 · ${progress}%`}</span></div>
        <p>{task.message}</p>
        {task.current_title && <p className="current-url">第 {task.current_index}/{task.discovered || task.fetched || '?'} 条：{task.current_title}</p>}
        {task.page_url && <p className="xhs-page">当前页面：{task.page_url}</p>}
        <div className="xhs-health"><span className={heartbeatAge !== null && heartbeatAge <= 5 ? 'healthy' : 'stale'}>{heartbeatAge !== null && heartbeatAge <= 5 ? '● 后台在线' : '● 心跳延迟'}</span>{active && progressAge > 45 && <strong>当前步骤已等待 {progressAge}s，将在超时后自动失败</strong>}</div>
        <div className="xhs-stats"><span>成功 <b>{task.success}</b></span><span>失败 <b>{task.failed}</b></span><span>耗时 <b>{elapsed}s</b></span><span>任务 <b>{task.task_id.slice(0, 8)}</b></span></div>
      </section>}
      {enabled ? active ? <div className="xhs-actions"><button className="button large" disabled>{statusLabel}</button><button className="button danger-button" disabled={task?.status === 'cancelling'} onClick={() => void cancel()}>{task?.status === 'cancelling' ? '正在取消…' : '取消任务'}</button></div> : <button className="button large" disabled={syncing} onClick={() => void run()}>开始读取收藏</button> : <a className="button large" href="/console/login/xiaohongshu">先连接已登录的 Chrome</a>}
      {result && <p className="success-text" role="status">{result}</p>}{error && <p className="error-text" role="alert">{error}</p>}
    </div>
  </Card>
}

function HistoricalMediaPanel() {
  const [items, setItems] = useState<MediaCandidate[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [provider, setProvider] = useState<any>(null)
  const [message, setMessage] = useState('')
  const load = useCallback(() => Promise.all([
    api<{ items: MediaCandidate[] }>('/api/xhs/media/candidates').then(value => setItems(value.items)),
    api<any>('/api/xhs/providers').then(setProvider),
  ]), [])
  useEffect(() => { void load() }, [load])
  const toggle = (id: string) => setSelected(previous => { const next=new Set(previous); if(next.has(id))next.delete(id);else next.add(id);return next })
  const start = () => api<XhsTask>('/api/xhs/media/reprocess', { method: 'POST', body: JSON.stringify({ item_ids: [...selected] }) }).then(value => { setMessage(`重处理任务已启动：${value.task_id?.slice(0,8)}`); setSelected(new Set()) }).catch(error => setMessage(error.message))
  return <Card title="历史视频重处理" action={<Badge status={provider?.opencli?.available ? 'configured' : 'unknown'}>{provider?.opencli?.available ? `OpenCLI ${provider.opencli.version}` : 'OpenCLI 不可用'}</Badge>}>
    <p className="hint">仅列出媒体、OCR、语音或完整度不足的视频；不会自动回填。</p>
    <div className="media-candidates">{items.length ? items.map(item => <label className="media-candidate" key={item.item_id}><input type="checkbox" checked={selected.has(item.item_id)} onChange={() => toggle(item.item_id)} /><span><strong>{item.title || '未命名视频'}</strong><small>媒体 {item.media_fetch_status} · OCR {item.ocr_status} · 语音 {item.transcription_status} · {item.content_completeness}</small></span></label>) : <p className="empty">暂无需要重处理的视频</p>}</div>
    <button className="button large" disabled={!selected.size} onClick={() => void start()}>重处理选中视频（{selected.size}）</button>
    {message && <p className="hint" role="status">{message}</p>}
  </Card>
}

function HotMemory() {
  const [content, setContent] = useState('正在加载…')
  const load = useCallback(() => api<{ content: string }>('/api/hot').then(value => setContent(value.content)), [])
  useEffect(() => { void load() }, [load])
  return <div className="app-shell"><header className="topbar"><div><p className="eyebrow">MEMFLOW</p><h1>hot.md / 项目记忆</h1></div><a className="button secondary" href="/console">返回 Dashboard</a></header><main className="memory-page"><Card title="hot.md 项目记忆" action={<button className="text-button" onClick={() => void load()}>刷新</button>}><div className="markdown"><ReactMarkdown components={{ a: props => <a {...props} target="_blank" rel="noreferrer" /> }}>{content}</ReactMarkdown></div></Card></main></div>
}

function XhsCenter({ account = false }: { account?: boolean }) {
  const [session, setSession] = useState<XhsSession | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(() => api<XhsSession>('/api/xhs/session').then(setSession), [])
  useEffect(() => { void load() }, [load])
  const start = () => api<XhsSession>('/api/xhs/login/chrome', { method: 'POST' }).then(value => { setSession(value); setError('') }).catch(e => setError(e.message))
  const refresh = () => api<XhsSession>('/api/xhs/session/refresh', { method: 'POST' }).then(setSession).catch(e => setError(e.message))
  const logout = () => api<XhsSession>('/api/xhs/logout', { method: 'POST' }).then(setSession).catch(e => setError(e.message))
  return <div className="app-shell"><header className="topbar"><div><p className="eyebrow">MEMFLOW AUTH</p><h1>Xiaohongshu / Account</h1></div><a className="button secondary" href="/console">Dashboard</a></header><main className="auth-page"><Card title={account ? 'Account management' : 'Xiaohongshu authorization'} action={<Badge status={session?.loggedIn ? 'configured' : 'unknown'}>{session?.loggedIn ? 'Logged in' : 'Logged out'}</Badge>}>
    {session?.loggedIn ? <div className="account-panel">{session.account.avatarUrl && <img className="avatar" src={session.account.avatarUrl} alt="avatar" />}<h3>{session.account.nickname || '小红书用户'}</h3><p>登录时间：{session.loginTime ? new Date(session.loginTime).toLocaleString() : '-'}</p><p>更新时间：{new Date(session.updatedAt).toLocaleString()}</p><div className="button-row"><button className="button" onClick={() => void start()}>重新连接 Chrome</button><button className="button secondary" onClick={() => void refresh()}>刷新会话</button><button className="button danger-button" onClick={() => void logout()}>退出登录</button></div></div> : <div className="qr-panel"><p>请先运行 scripts/start_chrome_cdp.ps1，并在专用 Chrome 中登录小红书。</p><button className="button" onClick={() => void start()}>连接当前 Chrome</button><p className="hint">默认连接 http://127.0.0.1:9223，仅在本机访问。</p></div>}
    {error && <p className="error-text" role="alert">{error}</p>}
  </Card></main></div>
}

export default function App() {
  const path = window.location.pathname
  const [config, setConfig] = useState<Config>(emptyConfig)
  const [inbox, setInbox] = useState<Inbox>(emptyInbox)
  const [task, setTask] = useState<Task>(emptyTask)
  const [recent, setRecent] = useState<RecentItem[]>([])
  const [notice, setNotice] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)
  const [queueText, setQueueText] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [xhsSession, setXhsSession] = useState<XhsSession | null>(null)
  const [notion, setNotion] = useState({ notion_token: '', notion_database_id: '' })

  if (path.endsWith('/login/xiaohongshu')) return <XhsCenter />
  if (path.endsWith('/settings/account')) return <XhsCenter account />
  if (path.endsWith('/memory')) return <HotMemory />

  const report = (promise: Promise<unknown>, success: string) => promise.then(() => setNotice({ tone: 'good', text: success })).catch((error: Error) => setNotice({ tone: 'bad', text: error.message }))
  const loadConfig = useCallback(() => api<Config>('/api/config/status').then(setConfig), [])
  const loadXhsSession = useCallback(() => api<XhsSession>('/api/xhs/session').then(setXhsSession), [])
  const loadInbox = useCallback(() => api<Inbox>('/api/inbox').then(setInbox), [])
  const loadTask = useCallback(() => api<Task>('/api/processor/status').then(setTask), [])
  const loadRecent = useCallback(() => api<{ items: RecentItem[] }>('/api/notion/recent').then(value => setRecent(value.items)), [])
  const refreshAll = useCallback(() => { void Promise.allSettled([loadConfig(), loadXhsSession(), loadInbox(), loadTask(), loadRecent()]) }, [loadConfig, loadXhsSession, loadInbox, loadTask, loadRecent])

  useEffect(refreshAll, [refreshAll])
  useEffect(() => {
    if (task.status !== 'processing') return
    const timer = window.setInterval(() => { void loadTask() }, 1000)
    return () => window.clearInterval(timer)
  }, [task.status, loadTask])
  useEffect(() => {
    if ((task.status === 'success' || task.status === 'failed') && task.task_id) void Promise.allSettled([loadInbox(), loadRecent()])
  }, [task.status, task.task_id, loadInbox, loadRecent])
  useEffect(() => { setSelectedIds(previous => new Set([...previous].filter(id => inbox.items.some(item => item.item_id === id)))) }, [inbox.items])

  async function saveNotion(event: FormEvent) {
    event.preventDefault(); await report(api('/api/config/notion', { method: 'POST', body: JSON.stringify(notion) }).then(() => { setNotion({ notion_token: '', notion_database_id: '' }); return loadConfig() }), 'Notion 配置已保存')
  }
  async function clearConfig(kind: 'notion') {
    if (!window.confirm('确定清除该配置吗？')) return
    await report(api(`/api/config/${kind}`, { method: 'DELETE' }).then(loadConfig), '配置已清除')
  }
  async function appendInbox(event: FormEvent) {
    event.preventDefault(); await report(api<Inbox>('/api/inbox', { method: 'POST', body: JSON.stringify({ content: queueText }) }).then(value => { setInbox(value); setQueueText('') }), '已加入待整理队列')
  }
  async function deleteItem(itemId: string) {
    if (!window.confirm('确定删除这条待处理内容吗？')) return
    await report(api<Inbox>('/api/inbox/item', { method: 'DELETE', body: JSON.stringify({ item_id: itemId, version: inbox.version }) }).then(setInbox), '已删除')
  }
  function toggleSelection(itemId: string) {
    setSelectedIds(previous => { const next=new Set(previous); if(next.has(itemId)) next.delete(itemId); else next.add(itemId); return next })
  }
  function toggleAll() {
    setSelectedIds(selectedIds.size === inbox.items.length ? new Set() : new Set(inbox.items.map(item => item.item_id)))
  }
  async function deleteSelected() {
    if (!selectedIds.size || !window.confirm(`确定删除选中的 ${selectedIds.size} 条内容吗？`)) return
    await report(api<Inbox>('/api/inbox/items', { method: 'DELETE', body: JSON.stringify({ item_ids: [...selectedIds], version: inbox.version }) }).then(value => { setInbox(value); setSelectedIds(new Set()) }), `已删除 ${selectedIds.size} 条内容`)
  }
  async function startProcessor() {
    await report(api<Task>('/api/processor/start', { method: 'POST' }).then(setTask), '整理任务已启动')
  }

  return <div className="app-shell">
    <header className="topbar"><div><p className="eyebrow">MEMFLOW</p><h1>Knowledge Console <span>/ 知识库控制台</span></h1><p>配置来源、整理收件箱，并把知识安全归档到 Notion。</p></div><button className="button secondary" onClick={refreshAll}>刷新全部</button></header>
    {notice && <div className={`notice ${notice.tone}`} role="status">{notice.text}<button aria-label="关闭提示" onClick={() => setNotice(null)}>×</button></div>}

    <main className="dashboard">
      <div className="config-column">
        <Card title="小红书授权" action={<Badge status={xhsSession?.loggedIn ? 'configured' : 'unknown'}>{xhsSession?.loggedIn ? '已登录' : '未登录'}</Badge>}>
          <p className="hint">{xhsSession?.loggedIn ? `当前账号：${xhsSession.account.nickname || '小红书用户'}` : '连接已登录的本机 Chrome，无需复制 Cookie。'}</p>
          <div className="button-row"><a className="button" href="/console/login/xiaohongshu">连接 Chrome</a><a className="button secondary" href="/console/settings/account">账号管理</a></div>
        </Card>

        <FavoriteSyncPanel enabled={Boolean(xhsSession?.loggedIn)} />
        <HistoricalMediaPanel />

        <Card title="Notion 数据库配置" action={<Badge status={config.notion.configured ? 'configured' : 'unknown'}>{config.notion.configured ? '已配置' : '未配置'}</Badge>}>
          <form onSubmit={saveNotion} className="form-stack">
            <label>Integration Token<input type="password" value={notion.notion_token} onChange={e => setNotion({ ...notion, notion_token: e.target.value })} placeholder={config.notion.token_saved ? `已保存，长度 ${config.notion.token_length}` : '粘贴 NOTION_TOKEN'} /></label>
            <label>Database ID<input value={notion.notion_database_id} onChange={e => setNotion({ ...notion, notion_database_id: e.target.value })} placeholder={config.notion.database_id || 'Notion Database ID'} /></label>
            <div className="button-row"><button className="button" type="submit">保存 Notion 配置</button><button className="button secondary" type="button" onClick={() => void report(api('/api/notion/test', { method: 'POST' }).then(loadConfig), '连接测试完成')}>测试连接</button><button className="text-button danger" type="button" onClick={() => void clearConfig('notion')}>清除</button></div>
          </form>
          <p className="hint">{config.notion.check.database_name || config.notion.check.message}</p>
          {config.notion.check.database_url && <a className="external-link" href={config.notion.check.database_url} target="_blank" rel="noreferrer">打开 Notion 数据库 ↗</a>}
        </Card>

        <Card title="项目记忆"><p className="hint">在独立页面查看和刷新 hot.md。</p><a className="button secondary" href="/console/memory">打开 hot.md</a></Card>
      </div>

      <div className="work-column">
        <Card title="待整理收件箱" action={<div className="head-actions"><Badge status="processing">{inbox.pending_item_count} 项 / {inbox.pending_url_count} 链接</Badge><button className="text-button" onClick={() => void loadInbox()}>刷新</button></div>}>
          <form onSubmit={appendInbox} className="form-stack"><label>粘贴文字或链接（一次粘贴的文字按一条处理）<textarea rows={6} value={queueText} onChange={e => setQueueText(e.target.value)} placeholder="多个链接可逐行粘贴，保存时会自动用空行分隔&#10;&#10;普通文字无论多少行，都作为一个整理单位" /></label><button className="button" disabled={!queueText.trim()}>加入待整理队列</button></form>
          <div className="selection-toolbar"><button className="button secondary compact" type="button" disabled={!inbox.items.length} onClick={toggleAll}>{selectedIds.size === inbox.items.length && inbox.items.length ? '取消全选' : '全选'}</button><span>已选择 {selectedIds.size} 条</span><button className="button danger-button compact" type="button" disabled={!selectedIds.size} onClick={() => void deleteSelected()}>删除选中</button></div>
          <div className="queue-list">{inbox.items.length === 0 ? <p className="empty">队列为空</p> : inbox.items.map(item => <article className={`queue-item ${selectedIds.has(item.item_id) ? 'selected' : ''}`} key={item.item_id}><label className="select-box"><input type="checkbox" aria-label={`选择 ${item.content.slice(0, 20)}`} checked={selectedIds.has(item.item_id)} onChange={() => toggleSelection(item.item_id)} /></label><div className="queue-content"><Badge status={item.status}>{item.status === 'failed' ? '处理失败' : '待处理'}</Badge><p>{item.content}</p>{item.failure_reason && <p className="error-text">{item.failure_reason}</p>}</div><button className="text-button danger" onClick={() => void deleteItem(item.item_id)}>删除</button></article>)}</div>
        </Card>

        <Card title="自动整理任务" action={<Badge status={task.status}>{({ idle: '空闲', processing: '处理中', success: '成功', failed: '失败' } as const)[task.status]}</Badge>}>
          <div className="task-grid"><div><strong>{task.processed}</strong><span>已处理</span></div><div><strong>{task.success}</strong><span>成功</span></div><div><strong>{task.skipped_duplicate}</strong><span>重复跳过</span></div><div><strong>{task.failed}</strong><span>失败</span></div></div>
          {task.current_url && <p className="current-url">正在处理：{task.current_url}</p>}{task.last_error && <p className="error-text">最近错误：{task.last_error}</p>}
          <button className="button large" disabled={task.status === 'processing' || inbox.pending_item_count === 0} onClick={() => void startProcessor()}>{task.status === 'processing' ? '正在整理…' : '开始整理'}</button>
        </Card>
      </div>

      <Card title="最近 Notion 整理结果" action={<button className="text-button" onClick={() => void loadRecent()}>刷新</button>} className="wide-card">
        <div className="result-list">{recent.length === 0 ? <p className="empty">暂无整理结果</p> : recent.map(item => <article className="result-item" key={item.item_id}><div><h3>{item.title}</h3><p>{new Date(item.created_at).toLocaleString()}</p><code>{item.normalized_url}</code></div><div className="result-actions"><Badge status="archived">已归档</Badge>{item.original_url && <a href={item.original_url} target="_blank" rel="noreferrer">原文 ↗</a>}{item.notion_url && <a href={item.notion_url} target="_blank" rel="noreferrer">Notion ↗</a>}</div></article>)}</div>
      </Card>

    </main>
    <footer>Knowledge Console · 敏感配置仅保存在本机后端</footer>
  </div>
}
