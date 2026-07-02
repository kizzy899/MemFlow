# 项目启动脚本

根目录的 `start.ps1` 为 Windows PowerShell 启动入口。脚本始终将工作目录切换到仓库根目录，使用 `.venv\Scripts\python.exe` 启动 FastAPI 应用，避免从其他目录调用时加载错误的相对路径。

小红书扫码登录需要持久 Playwright 会话，因此 Windows 启动脚本不启用 Uvicorn auto-reload，确保使用可创建 Chromium 子进程的 Proactor 事件循环。代码变更后需手动重启服务。

## 公共调用方式

```powershell
.\start.ps1
.\start.ps1 -BindAddress 0.0.0.0 -Port 8080
.\start.ps1 -NoReload
.\start.ps1 -Check
```

参数：

- `BindAddress`：监听地址，默认 `127.0.0.1`。
- `Port`：监听端口，默认 `8000`，有效范围为 1 到 65535。
- `NoReload`：关闭开发环境的自动重载。
- `Check`：只检查虚拟环境和 `uvicorn`，不启动服务。

## 数据、状态与失败行为

脚本不新增公共 HTTP API、持久化字段或业务状态流转。应用启动时仍由现有 lifespan 创建目录、初始化 SQLite 表并执行迁移。

缺少 `.venv` 时脚本立即失败并提示创建环境；虚拟环境中缺少 `uvicorn` 时提示安装 `requirements.txt`；缺少 `.env` 时仅发出警告，因为健康检查等不依赖外部服务的功能仍可运行。端口越界由 PowerShell 参数校验拒绝，应用异常退出会返回非零错误。

## 测试覆盖

- `powershell -ExecutionPolicy Bypass -File .\start.ps1 -Check`：验证解释器与 `uvicorn` 可用。
- 启动后请求 `GET /health`：验证服务可访问并返回 `{"status":"ok"}`。
- `python -m pytest -q`：执行现有应用回归测试。
