# Sales Audio Sync Handoff

交接目的：把本次聊天形成的需求、技术路线、已写代码、待安装软件、测试步骤交给下一位同事或 Codex 继续开发。

## 业务背景

公司销售会用手机电话和微信联系客户。用户希望把销售沟通数据进入电脑端销售管理系统，用于后续客户跟进、管理检查、录音转文字和自动生成销售跟进摘要。

早期讨论过在电脑端安装 OpenClaw/RPA 连接手机微信，定时抓取微信聊天和手机通话录音。经过讨论，认为：

- 抓个人微信聊天不稳定，微信没有普通企业可用的正式聊天记录 API。
- 抓微信和个人手机数据有较高隐私、劳动关系、客户个人信息合规风险。
- 老板暂时不想购买 API，因此不能依赖企业微信会话存档、电话系统 API 等商业方案。
- 更现实的低成本方案是先从公司配发安卓工作手机的通话录音做起。

最终路线：

```text
华为 Mate 50 Pro 公司工作手机
  -> 手机自动通话录音
  -> 同一 Wi-Fi 下用 Syncthing / FolderSync 同步到电脑本地目录
  -> Python 程序导入录音文件
  -> FFmpeg 转 16kHz mono WAV
  -> FunASR 语音转文字
  -> Ollama 本地大模型生成销售跟进摘要
  -> SQLite / 后续 CRM 数据库入库
```

## 合规和管理边界

当前建议：

- 使用公司配发安卓工作手机，不混用私人手机。
- 销售只用工作手机联系客户。
- 明确告知员工：工作手机通话录音会被同步到销售管理系统。
- 客户通话录音需要有明确提示或制度说明，特别是报价、合同、投诉、售后等敏感场景。
- 不抓个人微信聊天全文，第一阶段只做通话录音。
- 后续如果接入微信，优先考虑企业微信官方能力，而不是个人微信抓取。

## 当前代码状态

项目目录：

```text
sales-audio-sync/
  app/
    config.py
    adb_sync.py
    audio_convert.py
    transcribe.py
    summarize.py
    database.py
    local_import.py
    discover_phone.py
    pipeline.py
    scheduler.py
  data/
    inbox/
    recordings/
    wav/
    transcripts/
  db/
    sales_audio.db
  logs/
  README.md
  HANDOFF.md
  requirements.txt
```

核心文件说明：

- `app/local_import.py`：默认使用的本地同步模式，从 `data/inbox` 导入 Syncthing/FolderSync 同步过来的录音。
- `app/adb_sync.py`：保留的 ADB 模式，后续如 USB/ADB 修复可用。
- `app/discover_phone.py`：用于 ADB 模式下发现华为/安卓手机录音目录。
- `app/audio_convert.py`：调用 FFmpeg 转成 `16kHz mono wav`。
- `app/transcribe.py`：预留 FunASR 转文字。
- `app/summarize.py`：调用本地 Ollama 接口生成销售摘要。
- `app/database.py`：SQLite 表结构和状态流转。
- `app/pipeline.py`：一次执行完整流水线。
- `app/scheduler.py`：每天 23:30 自动执行。

默认模式已经改成：

```text
SYNC_MODE=local
LOCAL_INBOX_DIR=sales-audio-sync/data/inbox
```

也就是说，当前不依赖 USB，不依赖 ADB。

## 已验证内容

本机已检查：

- Python 已安装：`Python 3.10.8`
- `python -B -m compileall app` 通过
- SQLite 初始化通过
- 默认 `sync_mode` 为 `local`
- 默认 inbox 路径为：

```text
C:\Users\HYF05\Documents\Codex\2026-06-10\open-claw-open-claw\sales-audio-sync\data\inbox
```

本机缺少或未在 PATH 中检测到：

- FFmpeg
- Syncthing
- Ollama
- ADB
- Python 依赖：`apscheduler`, `requests`, `funasr`

当前决定：

- ADB 暂时不需要，因为走 Wi-Fi 同步路线。
- FunASR 暂时可以后装，先跑通录音同步和 FFmpeg 转码。

## 需要安装的软件

优先安装：

1. Python 3.10/3.11
   - 当前电脑已有 Python 3.10.8。

2. FFmpeg
   - 用于音频转码。
   - 安装后确认：

```powershell
ffmpeg -version
```

3. Syncthing Windows Setup
   - 用户截图里应选择：`Syncthing Windows Setup`
   - 不要选择 macOS 版。
   - `SyncTrayzor v2` 也可用，但初期建议先用官方 Windows Setup。

4. Ollama
   - 用于本地大模型摘要。
   - 安装后拉取模型：

```powershell
ollama pull qwen2.5:7b
```

5. Python 项目依赖

```powershell
cd C:\Users\HYF05\Documents\Codex\2026-06-10\open-claw-open-claw\sales-audio-sync
python -m pip install -r requirements.txt
```

后续安装：

- FunASR：等同步和转码跑通后再安装，避免一次性依赖太重。
- DB Browser for SQLite：可选，方便查看 `db/sales_audio.db`。

## 手机情况

用户手机：

```text
华为 Mate 50 Pro
```

已经进入开发者模式。曾尝试 USB，但 Windows 弹出：

```text
无法识别的 USB 设备
跟这台计算机连接的前一个 USB 设备工作不正常，Windows 无法识别它。
```

因此改为 Wi-Fi 同步方案。

如果以后继续排查 USB：

- 换支持数据传输的 USB 线。
- 换电脑 USB 口。
- 手机 USB 连接方式选择“传输文件 / MTP”。
- 安装华为手机助手 HiSuite 驱动。
- 手机开发者选项开启 USB 调试。

但当前路线不需要 USB。

## Syncthing 配置目标

电脑端 Syncthing 接收目录设为：

```text
C:\Users\HYF05\Documents\Codex\2026-06-10\open-claw-open-claw\sales-audio-sync\data\inbox
```

手机端选择华为通话录音目录作为同步源。可能路径包括：

```text
Sounds/CallRecord
Recordings/Call
CallRecord
Huawei/Recorder/Call
```

实际目录需要在华为文件管理器或录音/电话 App 中确认。

同步方向建议：

```text
手机发送 -> 电脑接收
```

避免电脑误删或覆盖手机录音。

## 运行方式

先安装依赖：

```powershell
cd C:\Users\HYF05\Documents\Codex\2026-06-10\open-claw-open-claw\sales-audio-sync
python -m pip install -r requirements.txt
```

把一段测试录音放进：

```text
sales-audio-sync\data\inbox
```

运行一次流水线：

```powershell
python -m app.pipeline
```

如果 FFmpeg 可用，程序会：

- 从 `data/inbox` 导入录音到 `data/recordings`
- 转 WAV 到 `data/wav`
- 写入 `db/sales_audio.db`

默认语音转文字和摘要是关闭的：

```text
ENABLE_TRANSCRIBE=0
ENABLE_SUMMARY=0
```

开启转文字和摘要：

```powershell
$env:ENABLE_TRANSCRIBE="1"
$env:ENABLE_SUMMARY="1"
python -m app.pipeline
```

运行定时任务：

```powershell
python -m app.scheduler
```

默认每天 Asia/Shanghai 时间 23:30 执行。

## 摘要格式

Ollama 摘要提示词要求输出：

```text
客户意向：
关键需求：
报价/产品：
异议点：
承诺事项：
下次跟进时间：
销售待办：
风险提醒：
```

要求只基于转写文本，不编造；缺失信息写“未提及”。

## 下一步建议

1. 安装 FFmpeg。
2. 安装 Syncthing Windows Setup。
3. 手机安装 Syncthing 或 Syncthing-Fork。
4. 手机打一通测试电话并确认生成录音。
5. 配置 Syncthing，把录音同步到 `data/inbox`。
6. 执行 `python -m app.pipeline`。
7. 查看 `data/recordings`, `data/wav`, `db/sales_audio.db` 是否有记录。
8. 安装 Ollama，拉取 `qwen2.5:7b`。
9. 安装和测试 FunASR。
10. 加一段真实销售电话录音测试转写准确率和摘要质量。

## 已知问题和待改进

- 当前没有从文件名解析手机号、通话时间、呼入/呼出。
- 当前没有 CRM 客户表，也没有客户号码匹配逻辑。
- 当前没有 Web 管理界面。
- 当前没有人工审核页面。
- 当前没有数据加密、权限控制、备份和保留策略。
- `__pycache__` 可能存在于项目中，但 `.gitignore` 已忽略，不影响运行。
- 当前 SQLite 是开发阶段选择，正式部署可换 MySQL/PostgreSQL/SQL Server。

## 给接手 Codex 的提示

用户希望继续完成“录音转文字 + 自动摘要 + 测试”。接手时优先不要扩大范围到微信抓取。当前最有价值的下一步是把本地同步目录里的测试音频跑通完整流水线，并补充：

- FFmpeg 路径检测和友好错误提示。
- 本地 inbox 样例测试。
- 数据库查看/导出脚本。
- FunASR 安装说明或可替换 faster-whisper。
- 文件名解析规则，可根据华为 Mate 50 Pro 实际录音文件名调整。
