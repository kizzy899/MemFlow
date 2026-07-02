# 小红书收藏读取操作流程

本文是 Windows 本机操作 Runbook，覆盖从启动 Chrome 到在 MemFlow 前端读取收藏的完整流程。无需复制 Cookie，也无需在前端执行 PowerShell。

## 一、首次准备

在仓库根目录 `D:\code\MemFlow` 打开 PowerShell。

### 1. 启动专用 Chrome

```powershell
.\scripts\start_chrome_cdp.ps1
```

脚本会：

- 使用 `data/chrome-cdp-profile` 作为独立、持久的浏览器资料目录；
- 只在本机 `127.0.0.1:9223` 开启 CDP；
- 打开小红书网页；
- 不修改日常 Chrome 的资料目录。

首次使用时，在新打开的专用 Chrome 中登录小红书，并手动确认“个人主页 → 收藏”可以打开。以后不要删除 `data/chrome-cdp-profile`，否则需要重新登录。

### 2. 验证 CDP

```powershell
Invoke-RestMethod http://127.0.0.1:9223/json/version
```

返回内容包含 `Browser` 和 `webSocketDebuggerUrl` 才表示 Playwright 可以连接。只有端口监听、但 `/json/version` 返回 404，不算可用 CDP。

项目不使用 Chrome 自身可能占用的 9222 授权服务，默认使用 9223。如需其他端口：

```powershell
.\scripts\start_chrome_cdp.ps1 -Port 9333
```

并在 `.env` 设置：

```env
CHROME_CDP_URL=http://127.0.0.1:9333
```

## 二、启动 MemFlow

保持专用 Chrome 开启，在另一个 PowerShell 窗口运行：

```powershell
.\start.ps1 -Port 8001 -NoReload
```

打开：

```text
http://127.0.0.1:8001/console/settings/account
```

修改代码或配置后必须按 `Ctrl+C` 停止服务，再重新执行启动命令。不要同时启动多个 8001 服务。

## 三、连接小红书账号

在账号管理页点击“连接当前 Chrome”。

后端会：

1. 连接 `CHROME_CDP_URL`；
2. 获取真实 Chrome 的默认浏览器上下文；
3. 检查小红书域下是否存在有效登录态；
4. 读取昵称和头像等公开账号摘要；
5. 将 storage state 加密保存到 `data/cookies/xiaohongshu.json`；
6. 向前端只返回登录状态和账号摘要，不返回 Cookie。

连接成功后状态显示为“已登录”。退出登录只删除 MemFlow 保存的会话，不会退出专用 Chrome 中的小红书账号。

## 四、读取收藏

连接成功后，账号管理页出现“读取收藏”面板。

1. 在“本次读取数量”输入 1–100，默认 20。
2. 点击“开始读取收藏”。
3. 等待按钮从“正在读取并整理…”恢复。
4. 页面显示成功整理条数，或显示后端错误。

前端实际发送：

```http
POST /api/xhs/sync
Content-Type: application/json

{"limit": 20}
```

后端在专用 Chrome 中新建临时标签，进入当前账号个人主页并点击“收藏”，读取完成后只关闭该临时标签。读取结果进入 MemFlow 本地整理与 Notion 同步流程。

## 五、日常使用顺序

每次使用按以下顺序：

1. 运行 `.\scripts\start_chrome_cdp.ps1`。
2. 确认专用 Chrome 已登录且保持开启。
3. 运行 `.\start.ps1 -Port 8001 -NoReload`。
4. 打开账号管理页并连接 Chrome。
5. 设置读取数量并开始读取收藏。
6. 完成后用 `Ctrl+C` 停止 MemFlow；需要时再关闭专用 Chrome。

## 六、常见问题

### CDP_UNAVAILABLE

- 检查专用 Chrome 是否开启；
- 检查 `http://127.0.0.1:9223/json/version`；
- 确认 `.env` 中 `CHROME_CDP_URL` 与脚本端口一致；
- 不要把只能返回 404 的 9222 Chrome 授权服务当作经典 CDP。

### CHROME_NOT_LOGGED_IN

在专用 Chrome 中登录小红书，并确认收藏页能手动打开，然后重新点击“连接当前 Chrome”。

### 端口 8001 已被占用

```powershell
netstat -ano | Select-String ':8001'
```

先关闭旧 MemFlow 终端，或根据确认后的 PID 停止旧进程，再重新启动。不要盲目终止不明进程。

### RISK_CONTROL / error_code=300012

这是小红书对当前出口 IP 的风控。关闭 VPN/代理并重试；仍失败时切换手机热点或其他正常网络。工具不能安全绕过平台风控。

### 收藏入口不可见

先在专用 Chrome 手动进入个人主页检查收藏页。如果手动可见但自动读取失败，记录页面变化和 `logs/login.log` 中的错误分类，不要记录或粘贴 Cookie。

## 七、安全边界

- CDP 只能监听 `127.0.0.1`，不得暴露到局域网或公网。
- `data/chrome-cdp-profile`、`data/cookies`、`.env` 和 `logs` 不得提交。
- 不在日志、Issue 或聊天中粘贴 Cookie、storage state、二维码或用户收藏原文。
- 专用 Chrome 开启期间，本机可连接 CDP 的程序拥有较高浏览器控制权限；仅在可信本机环境使用。
