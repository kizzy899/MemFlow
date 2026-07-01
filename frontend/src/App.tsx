import { FormEvent, useCallback, useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { api } from './api'

type Check = { status: string; message: string; database_name?: string; database_url?: string }
type Config = {
  xhs: { configured: boolean; cookie_saved: boolean; cookie_length: number; username_saved: boolean; username_masked: string; check: Check }
  notion: { configured: boolean; token_saved: boolean; token_length: number; database_id: string; check: Check }
}
type InboxItem = { item_id: string; content: string; urls: string[]; status: 'pending' | 'failed'; failure_reason: string }
type Inbox = { version: string; raw_content: string; pending_url_count: number; items: InboxItem[] }
type Task = { task_id: string | null; status: 'idle' | 'processing' | 'success' | 'failed'; current_url: string; processed: number; success: number; skipped_duplicate: number; failed: number; last_error: string }
type RecentItem = { item_id: string; title: string; original_url: string; normalized_url: string; notion_url: string; created_at: string; status: string }

const emptyConfig: Config = {
  xhs: { configured: false, cookie_saved: false, cookie_length: 0, username_saved: false, username_masked: '', check: { status: 'unknown', message: '尚未检测' } },
  notion: { configured: false, token_saved: false, token_length: 0, database_id: '', check: { status: 'unknown', message: '尚未检测' } },
}
const emptyInbox: Inbox = { version: '', raw_content: '', pending_url_count: 0, items: [] }
const emptyTask: Task = { task_id: null, status: 'idle', current_url: '', processed: 0, success: 0, skipped_duplicate: 0, failed: 0, last_error: '' }

function Card({ title, action, children, className = '' }: { title: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <section className={`card ${className}`}><div className="card-head"><h2>{title}</h2>{action}</div>{children}</section>
}

function Badge({ status, children }: { status: string; children: React.ReactNode }) {
  const tone = status === 'success' || status === 'configured' || status === 'archived' ? 'good' : status === 'failed' || status.includes('expire') ? 'bad' : status === 'processing' ? 'busy' : 'muted'
  return <span className={`badge ${tone}`}>{children}</span>
}

export default function App() {
  const [config, setConfig] = useState<Config>(emptyConfig)
  const [inbox, setInbox] = useState<Inbox>(emptyInbox)
  const [task, setTask] = useState<Task>(emptyTask)
  const [recent, setRecent] = useState<RecentItem[]>([])
  const [hot, setHot] = useState('暂无项目记忆')
  const [notice, setNotice] = useState<{ tone: 'good' | 'bad'; text: string } | null>(null)
  const [queueText, setQueueText] = useState('')
  const [xhs, setXhs] = useState({ xhs_cookie: '', xhs_username: '', xhs_password: '' })
  const [notion, setNotion] = useState({ notion_token: '', notion_database_id: '' })

  const report = (promise: Promise<unknown>, success: string) => promise.then(() => setNotice({ tone: 'good', text: success })).catch((error: Error) => setNotice({ tone: 'bad', text: error.message }))
  const loadConfig = useCallback(() => api<Config>('/api/config/status').then(setConfig), [])
  const loadInbox = useCallback(() => api<Inbox>('/api/inbox').then(setInbox), [])
  const loadTask = useCallback(() => api<Task>('/api/processor/status').then(setTask), [])
  const loadRecent = useCallback(() => api<{ items: RecentItem[] }>('/api/notion/recent').then(value => setRecent(value.items)), [])
  const loadHot = useCallback(() => api<{ content: string }>('/api/hot').then(value => setHot(value.content)), [])
  const refreshAll = useCallback(() => { void Promise.allSettled([loadConfig(), loadInbox(), loadTask(), loadRecent(), loadHot()]) }, [loadConfig, loadInbox, loadTask, loadRecent, loadHot])

  useEffect(refreshAll, [refreshAll])
  useEffect(() => {
    if (task.status !== 'processing') return
    const timer = window.setInterval(() => { void loadTask() }, 1000)
    return () => window.clearInterval(timer)
  }, [task.status, loadTask])
  useEffect(() => {
    if ((task.status === 'success' || task.status === 'failed') && task.task_id) void Promise.allSettled([loadInbox(), loadRecent(), loadHot()])
  }, [task.status, task.task_id, loadInbox, loadRecent, loadHot])

  async function saveXhs(event: FormEvent) {
    event.preventDefault(); await report(api('/api/config/xhs', { method: 'POST', body: JSON.stringify(xhs) }).then(() => { setXhs({ xhs_cookie: '', xhs_username: '', xhs_password: '' }); return loadConfig() }), '小红书配置已保存')
  }
  async function saveNotion(event: FormEvent) {
    event.preventDefault(); await report(api('/api/config/notion', { method: 'POST', body: JSON.stringify(notion) }).then(() => { setNotion({ notion_token: '', notion_database_id: '' }); return loadConfig() }), 'Notion 配置已保存')
  }
  async function clearConfig(kind: 'xhs' | 'notion') {
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
  async function startProcessor() {
    await report(api<Task>('/api/processor/start', { method: 'POST' }).then(setTask), '整理任务已启动')
  }

  return <div className="app-shell">
    <header className="topbar"><div><p className="eyebrow">MEMFLOW</p><h1>Knowledge Console <span>/ 知识库控制台</span></h1><p>配置来源、整理收件箱，并把知识安全归档到 Notion。</p></div><button className="button secondary" onClick={refreshAll}>刷新全部</button></header>
    {notice && <div className={`notice ${notice.tone}`} role="status">{notice.text}<button aria-label="关闭提示" onClick={() => setNotice(null)}>×</button></div>}

    <main className="dashboard">
      <div className="config-column">
        <Card title="小红书登录配置" action={<Badge status={config.xhs.configured ? 'configured' : 'unknown'}>{config.xhs.configured ? '已配置' : '未配置'}</Badge>}>
          <form onSubmit={saveXhs} className="form-stack">
            <label>Cookie<input type="password" value={xhs.xhs_cookie} onChange={e => setXhs({ ...xhs, xhs_cookie: e.target.value })} placeholder={config.xhs.cookie_saved ? `已保存，长度 ${config.xhs.cookie_length}` : '粘贴 XHS_COOKIE'} /></label>
            <label>用户名（可选）<input value={xhs.xhs_username} onChange={e => setXhs({ ...xhs, xhs_username: e.target.value })} placeholder={config.xhs.username_masked || '仅保存，不用于自动登录'} /></label>
            <label>密码（可选）<input type="password" value={xhs.xhs_password} onChange={e => setXhs({ ...xhs, xhs_password: e.target.value })} /></label>
            <div className="button-row"><button className="button" type="submit">保存小红书配置</button><button className="button secondary" type="button" onClick={() => void report(api('/api/xiaohongshu/test', { method: 'POST' }).then(loadConfig), '登录检测完成')}>测试登录</button><button className="text-button danger" type="button" onClick={() => void clearConfig('xhs')}>清除</button></div>
          </form>
          <p className="hint">{config.xhs.check.message}</p>
        </Card>

        <Card title="Notion 数据库配置" action={<Badge status={config.notion.configured ? 'configured' : 'unknown'}>{config.notion.configured ? '已配置' : '未配置'}</Badge>}>
          <form onSubmit={saveNotion} className="form-stack">
            <label>Integration Token<input type="password" value={notion.notion_token} onChange={e => setNotion({ ...notion, notion_token: e.target.value })} placeholder={config.notion.token_saved ? `已保存，长度 ${config.notion.token_length}` : '粘贴 NOTION_TOKEN'} /></label>
            <label>Database ID<input value={notion.notion_database_id} onChange={e => setNotion({ ...notion, notion_database_id: e.target.value })} placeholder={config.notion.database_id || 'Notion Database ID'} /></label>
            <div className="button-row"><button className="button" type="submit">保存 Notion 配置</button><button className="button secondary" type="button" onClick={() => void report(api('/api/notion/test', { method: 'POST' }).then(loadConfig), '连接测试完成')}>测试连接</button><button className="text-button danger" type="button" onClick={() => void clearConfig('notion')}>清除</button></div>
          </form>
          <p className="hint">{config.notion.check.database_name || config.notion.check.message}</p>
          {config.notion.check.database_url && <a className="external-link" href={config.notion.check.database_url} target="_blank" rel="noreferrer">打开 Notion 数据库 ↗</a>}
        </Card>
      </div>

      <div className="work-column">
        <Card title="待整理收件箱" action={<div className="head-actions"><Badge status="processing">{inbox.pending_url_count} 个链接</Badge><button className="text-button" onClick={() => void loadInbox()}>刷新</button></div>}>
          <form onSubmit={appendInbox} className="form-stack"><label>粘贴文字或链接（一次粘贴的文字按一条处理）<textarea rows={6} value={queueText} onChange={e => setQueueText(e.target.value)} placeholder="多个链接可逐行粘贴，保存时会自动用空行分隔&#10;&#10;普通文字无论多少行，都作为一个整理单位" /></label><button className="button" disabled={!queueText.trim()}>加入待整理队列</button></form>
          <div className="queue-list">{inbox.items.length === 0 ? <p className="empty">队列为空</p> : inbox.items.map(item => <article className="queue-item" key={item.item_id}><div><Badge status={item.status}>{item.status === 'failed' ? '处理失败' : '待处理'}</Badge><p>{item.content}</p>{item.failure_reason && <p className="error-text">{item.failure_reason}</p>}</div><button className="text-button danger" onClick={() => void deleteItem(item.item_id)}>删除</button></article>)}</div>
        </Card>

        <Card title="自动整理任务" action={<Badge status={task.status}>{({ idle: '空闲', processing: '处理中', success: '成功', failed: '失败' } as const)[task.status]}</Badge>}>
          <div className="task-grid"><div><strong>{task.processed}</strong><span>已处理</span></div><div><strong>{task.success}</strong><span>成功</span></div><div><strong>{task.skipped_duplicate}</strong><span>重复跳过</span></div><div><strong>{task.failed}</strong><span>失败</span></div></div>
          {task.current_url && <p className="current-url">正在处理：{task.current_url}</p>}{task.last_error && <p className="error-text">最近错误：{task.last_error}</p>}
          <button className="button large" disabled={task.status === 'processing' || inbox.pending_url_count === 0} onClick={() => void startProcessor()}>{task.status === 'processing' ? '正在整理…' : '开始整理'}</button>
        </Card>
      </div>

      <Card title="最近 Notion 整理结果" action={<button className="text-button" onClick={() => void loadRecent()}>刷新</button>} className="wide-card">
        <div className="result-list">{recent.length === 0 ? <p className="empty">暂无整理结果</p> : recent.map(item => <article className="result-item" key={item.item_id}><div><h3>{item.title}</h3><p>{new Date(item.created_at).toLocaleString()}</p><code>{item.normalized_url}</code></div><div className="result-actions"><Badge status="archived">已归档</Badge>{item.original_url && <a href={item.original_url} target="_blank" rel="noreferrer">原文 ↗</a>}{item.notion_url && <a href={item.notion_url} target="_blank" rel="noreferrer">Notion ↗</a>}</div></article>)}</div>
      </Card>

      <Card title="hot.md 项目记忆" action={<button className="text-button" onClick={() => void loadHot()}>刷新</button>} className="wide-card memory-card"><div className="markdown"><ReactMarkdown components={{ a: props => <a {...props} target="_blank" rel="noreferrer" /> }}>{hot}</ReactMarkdown></div></Card>
    </main>
    <footer>Knowledge Console · 敏感配置仅保存在本机后端</footer>
  </div>
}