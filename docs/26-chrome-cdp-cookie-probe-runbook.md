# Chrome CDP 启动与小红书 Cookie 探测修复流程

本文记录 `scripts\start_chrome_cdp.ps1` 的稳定启动流程。目标是在 MemFlow 后端启动前，先确认 Chrome CDP 不只是端口可用，而且能通过 DevTools WebSocket 读取小红书域名下的 Cookie 状态。

## 修复后的启动顺序

1. 在 Windows PowerShell 中进入仓库根目录 `D:\code\MemFlow`。
2. 执行 `.\scripts\start_chrome_cdp.ps1`。
3. 脚本先检查 `http://127.0.0.1:<port>/json/version`，必须返回 `webSocketDebuggerUrl` 才算 CDP 可用。
4. 脚本读取 `http://127.0.0.1:<port>/json/list`，查找已打开的小红书 page target。
5. 如果没有小红书 target，脚本通过 CDP 打开 `https://www.xiaohongshu.com/explore` 并等待 target 出现。
6. 脚本连接该 target 的 DevTools WebSocket，执行 `Network.enable` 和 `Network.getCookies`。
7. 脚本只输出 Cookie 数量和是否检测到 `a1` / `web_session`，不会输出 Cookie 值。
8. 读取链路成功后，再启动 MemFlow 或在前端点击“连接当前 Chrome”。

## 常用命令

```powershell
.\scripts\start_chrome_cdp.ps1
.\scripts\start_chrome_cdp.ps1 -Port 9333
.\scripts\start_chrome_cdp.ps1 -RequireXhsLogin
.\scripts\start_chrome_cdp.ps1 -SkipCookieProbe
```

参数说明：

- `Port`：Chrome CDP 本机端口，默认 `9223`。
- `StartupTimeoutSec`：等待 `/json/version` 可用的时间，默认 `30` 秒。
- `CookieProbeTimeoutSec`：等待小红书 target 与 Cookie 探测的时间，默认 `20` 秒。
- `RequireXhsLogin`：未检测到 `a1` 或 `web_session` 时直接失败，适合正式读取收藏前的强校验。
- `SkipCookieProbe`：只验证 CDP 端点，跳过小红书 Cookie 探测，适合排查 Chrome 启动本身。

## 成功与失败行为

成功时会看到类似输出：

```text
Chrome CDP is ready at http://127.0.0.1:9223
Xiaohongshu cookie state is readable via Chrome CDP. Cookie count: 14.
Xiaohongshu login cookies detected: a1, web_session.
```

如果 Cookie 可读但未登录，默认只给出 warning，方便首次使用时先打开 Chrome 登录；加上 `-RequireXhsLogin` 后会失败退出。端口被非 CDP 进程占用、`/json/version` 没有 `webSocketDebuggerUrl`、小红书 target 无法打开、DevTools WebSocket 无法执行 `Network.getCookies` 时，脚本直接失败并阻止后续启动链路误判为可用。

## API、持久化与安全

本次修复不新增 HTTP API、数据库字段、Notion schema 或业务状态流转。脚本只通过本机 Chrome CDP 读取运行时 Cookie 状态，不写入 Cookie，不保存 Cookie 值，也不把 Cookie 值输出到日志或终端。

持久化仍沿用既有边界：Chrome 资料目录位于 `data/chrome-cdp-profile`，MemFlow 加密会话位于 `data/cookies/xiaohongshu.json`。这两个目录均不得提交。CDP 仍限定在 `127.0.0.1`，不得暴露到局域网或公网。

## 验证结果

- PowerShell 语法解析通过：`[scriptblock]::Create((Get-Content -Raw scripts/start_chrome_cdp.ps1))`。
- `.\scripts\start_chrome_cdp.ps1 -SkipCookieProbe` 返回 Chrome CDP ready。
- `.\scripts\start_chrome_cdp.ps1` 返回 Cookie 状态可读，并检测到 `a1` 与 `web_session`。
- `git diff --check` 通过。