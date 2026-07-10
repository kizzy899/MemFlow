# 项目启动脚本

根目录的 `start.ps1` 为 Windows PowerShell 启动入口。脚本始终将工作目录切换到仓库根目录，先启动本机 Chrome CDP，再使用 `.venv\Scripts\python.exe` 启动 FastAPI 应用，避免从其他目录调用时加载错误的相对路径。

小红书扫码登录需要持久 Playwright 会话，因此 Windows 启动脚本不启用 Uvicorn auto-reload，确保使用可创建 Chromium 子进程的 Proactor 事件循环。代码变更后需手动重启服务。

## 公共调用方式

```powershell
.\start.ps1
.\start.ps1 -BindAddress 0.0.0.0 -Port 8080
.\start.ps1 -NoReload
.\start.ps1 -ChromeCdpPort 9333
.\start.ps1 -Check
```

参数：

- `BindAddress`：监听地址，默认 `127.0.0.1`。
- `Port`：MemFlow HTTP 监听端口，默认 `8000`，有效范围为 1 到 65535。
- `ChromeCdpPort`：启动专用 Chrome CDP 的本机端口，默认 `9223`，有效范围为 1024 到 65535；如 `.env` 中 `CHROME_CDP_URL` 使用其他端口，启动时应传入相同端口。
- `NoReload`：关闭开发环境的自动重载。
- `Check`：只检查虚拟环境和 `uvicorn`，不启动服务。

## 数据、状态与失败行为

脚本不新增公共 HTTP API、持久化字段或业务状态流转。应用启动时仍由现有 lifespan 创建目录、初始化 SQLite 表并执行迁移。非 `-Check` 启动会先调用 `scripts\start_chrome_cdp.ps1 -Port <ChromeCdpPort>`；该脚本复用 `data\chrome-cdp-profile`，并且会验证 `http://127.0.0.1:<port>/json/version` 返回 `webSocketDebuggerUrl`。端口已监听但不是 Chrome CDP 时脚本会失败，不会让后端带着不可用 CDP 继续启动。

缺少 `.venv` 时脚本立即失败并提示创建环境；虚拟环境中缺少 `uvicorn` 时提示安装 `requirements.txt`；缺少 `.env` 时仅发出警告，因为健康检查等不依赖外部服务的功能仍可运行。端口越界由 PowerShell 参数校验拒绝。Chrome 不存在、CDP 启动脚本缺失或 CDP 脚本失败时，MemFlow 后端不会继续启动；应用异常退出会返回非零错误。`-Check` 只验证虚拟环境和 `uvicorn`，不会启动 Chrome 或服务。

## 测试覆盖

- `powershell -ExecutionPolicy Bypass -File .\start.ps1 -Check`：验证解释器与 `uvicorn` 可用。
- 非 `-Check` 启动：验证日志先出现 Chrome CDP ready 提示，再出现 MemFlow 服务地址。
- 启动后请求 `GET /health`：验证服务可访问并返回 `{"status":"ok"}`。
- `python -m pytest -q`：执行现有应用回归测试。
