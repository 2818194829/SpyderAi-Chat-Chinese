# SpyderAi-Chat-Chinese

**Spyder 6.x** 的 AI 聊天插件（中文汉化版）—— 基于 **spyder-ai-chat** v0.8.8 全面汉化。

开箱即用支持 **12 个 AI 提供商** —— OpenAI、Groq、Mistral、DeepSeek、Together AI、Fireworks AI、OpenRouter、Azure OpenAI、Ollama、LM Studio、vLLM，以及任何自定义 OpenAI 兼容端点 —— 全部在 IDE 内部完成，无需切换窗口。

© 2026 Maciej Piecko · 中文汉化版 — MIT 许可证

---

## ✨ 功能特性

### 💬 聊天界面
| 功能 | 说明 |
|---|---|
| 🗨️ 聊天 UI | 可滚动的对话界面，用户/AI 消息颜色区分 |
| ⚡ 流式输出 | Token 级流式传输，增量 Markdown 渲染 —— 已完成的块实时格式化显示 |
| 🔁 模型选择 | 下拉框从 API 实时拉取模型列表，随时切换模型 |
| 🔧 12 个提供商 | OpenAI、Groq、Mistral、DeepSeek、Together、Fireworks、OpenRouter、Azure、Ollama、LM Studio、vLLM、自定义 |
| ⚙ 推理参数 | 每轮聊天的温度、最大 Token、top-p、top-k、min-p、惩罚项、随机种子、num_ctx —— 按提供商自动适配（只显示相关参数） |
| 🔑 可选 API 密钥 | 本地模型无需密钥认证可留空 |
| 🧠 系统提示词 | 自定义系统提示词字段，或从已保存的提示词库中选择 |
| 💬 已保存系统提示词 | 定义可复用的系统提示词；通过 设置 → 系统提示词 标签页管理 |
| ⏹ 停止 | 随时取消正在流式输出的回复 |
| 🗑 新聊天 | 开始新对话，当前对话自动保存 |
| 🔄 重新生成 | 一键重新运行上一条 AI 回复 |

### 📋 聊天历史
| 功能 | 说明 |
|---|---|
| 📋 聊天历史 | 浏览、加载和删除已保存的聊天；按标题或内容实时搜索；当前聊天绿色高亮 |
| 📄 聊天历史分页 | 超过 120 条消息的聊天自动分页；底部居中显示 `<<` / `<` / 页码 / `>` / `>>` 导航栏；当前页高亮；短聊天自动隐藏分页栏 |
| 🗂 聊天集合 | 将聊天组织到命名集合中；通过 ⚙ 管理器创建、重命名和删除集合；右键菜单移动聊天到其他集合；可在单个集合或全部集合中搜索 |

### 📎 上下文管理
| 功能 | 说明 |
|---|---|
| 📎 文件上下文 | 附加编辑器中的完整文件或选中文本、IPython 控制台输出作为上下文 —— 输入栏中显示彩色标签；编辑器快捷键 **Ctrl+Shift+A**（添加文件）和 **Ctrl+Shift+Q**（添加选中内容） |
| 📁 项目上下文 | 通过 **📁 项目上下文** 开关将整个 Spyder 项目附加到聊天 —— 文件夹选择、增量更新、未保存编辑的实时缓冲区、文件变更检测 |
| 📊 上下文大小估计 | 参数栏中始终可见的 `~X.Xk / Yk (Z%)` Token 计数器 —— 按使用级别颜色编码；悬停显示按类别细分弹窗（历史、系统提示词、上下文文件、压缩缓冲区） |

### 🖊️ Markdown 渲染
| 功能 | 说明 |
|---|---|
| 🖊️ Markdown 渲染 | 标题、粗体、斜体、表格、代码块（可横向滚动）、引用、链接、删除线 |
| 🗂 嵌套列表 | 任意深度的有序和无序列表、混合类型、空行分隔项 |
| 🧠 思考块 | `<think>` 标签渲染为可折叠可滚动的思考框（DeepSeek-R1、QwQ、Qwen-thinking 等） |
| 📋 复制到编辑器 | 将任意代码块或完整回复插入到当前文件的光标位置 |
| 🗑 删除对话 | 删除任意一轮对话（3 秒撤销窗口）；或清除某点之前的所有对话 |

### ⚙ 设置（9 个标签页）
| 标签页 | 说明 |
|---|---|
| 🔌 连接 | 提供商选择 + 动态 URL/密钥/额外字段表单 + 测试连接按钮 |
| 🖊 对话框 | 独立配置各渲染元素的字体大小（6–24 pt） |
| 🗂 历史 | 自动保存开关 |
| ⎇ Git 状态栏 | 显示 Git 状态栏（分支、未提交更改、快速操作按钮）；刷新间隔设置 |
| 📁 上下文 | LLM 项目上下文限制 + 上下文历史压缩（截断 / LLM 总结策略） |
| 💬 系统提示词 | 管理可复用的系统提示词 |
| / 命令 | 定义斜杠命令别名；内置命令（只读）显示在单独区域 |
| ⚡ 自动补全 | AI 驱动的 FIM（Fill-In-Middle）代码补全配置 |
| 🤖 代理 | 代理模式主开关、自主模式选择、允许的操作类型、基础路径 |

### / 命令系统
| 命令 | 类型 | 说明 |
|---|---|---|
| `/tests` | 默认 | 为代码生成全面的单元测试 |
| `/simplify` | 默认 | 简化代码 |
| `/fix` | 默认 | 修复代码中的所有问题 |
| `/explain` | 默认 | 解释代码的工作原理 |
| `/doc` | 默认 | 为代码添加文档注释 |
| `/clear` | 内置 | 清除所有消息，保留模型、系统提示词和所有设置 |
| `/compact` | 内置 | 手动触发 LLM 总结压缩聊天历史 |

### ✍️ AI 自动补全（FIM）
- **支持的后端**：Ollama（原生 FIM）、OpenAI 兼容 `/v1/completions`、Codestral/Mistral、聊天补全（提示注入后备方案）
- **模型参数**：最大 Token、温度、光标前后文窗口
- **触发模式**：*自动*（输入暂停后触发，默认 600 ms）、*仅新行后*、*仅手动*（Alt+\\）
- 灰色幽灵文本显示在光标后，按 **Tab** 接受，**Escape** 取消

### 🤖 代理模式
LLM 可使用特殊代码围栏执行实际操作：
| 操作 | 围栏语法 | 说明 |
|---|---|---|
| 📄 创建/覆盖文件 | `` ```file:path/to/file.py `` | 创建新文件或覆盖已有文件 |
| ▶ 在控制台运行 | `` ```run:python `` | 在 IPython 控制台中执行 Python 代码 |
| 📦 安装包 | `` ```install:pip `` | 通过 pip 安装 Python 包 |
| 🩹 应用补丁 | `` ```patch:path/to/file.py `` | 对已有文件应用统一差异补丁 |
| ⎇ Git 命令 | `` ```run:git `` | 执行 git 命令 |
| 📄 读取文件 | `` ```read:path/to/file.py `` | 读取文件内容或指定行范围 |
| 📁 列出目录 | `` ```ls:path/to/dir/ `` | 列出目录内容 |
| 🔍 搜索文件 | `` ```grep:pattern `` | 在项目中搜索正则表达式模式 |
| 🗑 删除文件/目录 | `` ```delete:path `` | 删除文件或目录（不可逆） |
| ↪ 重命名 | `` ```rename:old_path `` | 重命名或移动文件/目录 |

**自主模式**：手动（批量对话框，不自动发送）、半自动（批量对话框+自动发送）、完全（静默或确认修改）

### ⎇ Git 状态栏
- 显示当前分支名称、未提交的差异统计
- 快速操作：**提交**（生成提交信息）、**PR 描述**（编写拉取请求描述）、**更改**（总结未提交更改）

### 📁 项目上下文
- 首条消息发送全部文件；后续消息仅发送变更文件（增量）
- 未保存文件使用编辑器实时缓冲区
- 内置排除 .git、\_\_pycache\_\_、\*.pyc、.venv、node_modules 等

### ⚡ 上下文历史压缩
- **截断**：超过限制时静默丢弃最早消息
- **LLM 总结**：让 LLM 编写总结，保存为压缩块供后续使用

### 📊 Token 计数器
- 始终显示估计 Token 数（灰色=正常、琥珀色=接近阈值、红色=超出限制）
- 悬停显示带分类明细的深色浮动弹窗

---

## 📥 安装

### 从源码安装（推荐）
```bash
cd SpyderAi-Chat-Chinese
pip install -e .
```
> **重要：** 请安装到 **Spyder 使用的同一 Python 环境**中。
> 如果从 conda 环境启动 Spyder，请先激活该环境：
> ```bash
> conda activate Positron
> pip install -e .
> ```

安装后 **重启 Spyder**。插件自动出现；若不可见请前往 **窗口 → 窗格 → AI 聊天**。

---

## ⚙ 配置详情

点击 AI 聊天窗格工具栏中的 **⚙ 设置** 按钮打开标签式设置对话框。

### 🔌 连接
| 提供商 | 默认 URL | API 密钥 |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | 必需 |
| Groq | `https://api.groq.com/openai/v1` | 必需 |
| Mistral AI | `https://api.mistral.ai/v1` | 必需 |
| DeepSeek | `https://api.deepseek.com` | 必需 |
| Together AI | `https://api.together.xyz/v1` | 必需 |
| Fireworks AI | `https://api.fireworks.ai/inference/v1` | 必需 |
| OpenRouter | `https://openrouter.ai/api/v1` | 必需 |
| Azure OpenAI | `https://<资源名>.openai.azure.com/…` | 必需 + 部署名 + API 版本 |
| Ollama（本地） | `http://localhost:11434/v1` | 不需要 |
| LM Studio（本地） | `http://localhost:1234/v1` | 可选 |
| vLLM | `http://localhost:8000/v1` | 可选 |
| 自定义 | *（任意 URL）* | 可选 |

**测试连接** 按钮发送 `GET /models` 探测到配置端点，报告可用模型数量。

### 🖊 对话框字体
基础文本（10 pt）、代码块（10 pt）、标题 H1 基准（14 pt）、列表（10 pt）、表格（10 pt）、思考框（9 pt）。范围 6–24 pt。更改在保存后应用于新消息。

### 🗂 历史
- **自动保存聊天记录到历史**：每轮对话自动写入磁盘
- **开始新聊天时保存未发送的聊天**：关闭自动保存时有效

### ⎇ Git 状态栏
- 显示分支名、未提交差异统计
- **提交** → 收集 `git status` 和 `git diff`，让 LLM 建议提交信息
- **PR 描述** → 对比主分支，让 LLM 编写 PR 描述
- **更改** → 总结所有未提交更改
- 刷新间隔可配置（5–300 秒）

### 📁 上下文
**LLM 项目上下文**：最大文件大小、最大文件数、额外排除 glob 模式、新聊天时重置
**上下文历史压缩**：启用/禁用、策略选择（截断/LLM 总结）、触发阈值、各模型 Token 限制表、默认 Token 限制

### 💬 系统提示词
管理可复用的系统提示词。选择后立即编辑，**💾 保存**按钮仅在内容变更时激活。可设置新聊天的默认提示词。

### / 命令
内置命令（`/clear`、`/compact`）只读显示。用户可自定义命令（名称≥2字符，不含前导/）。支持恢复内置默认值。

### ⚡ 自动补全
1. 勾选启用 → 2. 选择提供商和 URL → 3. 点击**加载模型** → 4. 选择模型和后端类型
支持后端：Ollama（/api/generate）、OpenAI 兼容（/v1/completions）、Codestral（/v1/fim/completions）、聊天补全（后备）
模型参数：最大 Token、温度、光标前后文（字符数）

### 🤖 代理
全局启用/禁用。自主模式：手动、半自动、完全。可独立允许/禁止每种操作类型。可设置文件路径的默认基础路径。实时预览代理系统提示词。

---

## 📁 项目结构
```
spyder_ai_chat/
├── __init__.py              # 版本信息
├── plugin.py                # 插件主入口（SpyderDockablePlugin）
├── confpage.py              # 偏好设置页面
├── resources/               # 图标等资源文件
├── widgets/                 # 前端 UI 组件
│   ├── chat_widget.py       # 主聊天窗口
│   ├── settings_dialog.py   # 设置对话框（9 个标签页）
│   ├── chat_history_manager.py # 聊天历史管理
│   ├── collection_manager.py   # 聊天集合管理
│   ├── markdown_renderer.py    # Markdown 渲染器
│   ├── system_prompts.py       # 系统提示词管理
│   ├── commands.py             # 斜杠命令系统
│   ├── project_context.py      # 项目上下文管理
│   └── agentic_actions.py      # 代理模式动作执行
└── fim/                     # FIM 代码补全模块
    ├── provider.py           # Spyder Completions API 适配
    ├── ghost_text.py         # 幽灵文本渲染管理器
    ├── client.py             # FIM API 客户端
    ├── config.py             # FIM 配置
    └── widgets/status.py     # FIM 状态指示器
```

---

## 📜 许可证
MIT License — 详见 [LICENSE](LICENSE) 文件。

原始项目：© 2026 Maciej Piecko · [spyder-ai-chat](https://sourceforge.net/projects/spyder-ai-chat-plugin/)

| Provider | Default URL | API key |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | Required |
| Groq | `https://api.groq.com/openai/v1` | Required |
| Mistral AI | `https://api.mistral.ai/v1` | Required |
| DeepSeek | `https://api.deepseek.com` | Required |
| Together AI | `https://api.together.xyz/v1` | Required |
| Fireworks AI | `https://api.fireworks.ai/inference/v1` | Required |
| OpenRouter | `https://openrouter.ai/api/v1` | Required |
| Azure OpenAI | `https://<resource>.openai.azure.com/…` | Required + deployment name + API version |
| Ollama (local) | `http://localhost:11434/v1` | Not required |
| LM Studio (local) | `http://localhost:1234/v1` | Optional |
| vLLM | `http://localhost:8000/v1` | Optional |
| Custom | *(any URL)* | Optional |

A **Test Connection** button sends a `GET /models` probe to the configured endpoint and reports how many models are available, helping verify credentials and reachability before saving.

### Tab 2 — Dialogs

Configure font sizes (6–24 pt) for each rendered element independently:

| Setting | Default | Affects |
|---|---|---|
| Base text | 10 pt | Paragraphs, blockquotes |
| Code blocks | 10 pt | Fenced code block content |
| Headings (H1 base) | 14 pt | H1 = base, H2 = base−2, H3 = base−4 |
| Lists | 10 pt | Bullet and numbered lists |
| Tables | 10 pt | Table header and data cells |
| Thinking box | 9 pt | `<think>` block content |

Changes apply to new messages rendered after saving.

### Tab 3 — History

- **Automatically save chats to history** — when on, every completed exchange is written to disk silently.
- **Save unsent chat when starting New Chat** — only relevant when auto-save is off; gives a one-time save at the moment you click New Chat.

### Tab 4 — Context

Configure limits and exclusion rules for the **📁 Proj. Context** feature.

- **Max file size** — files larger than this limit are skipped when collecting project context.
- **Max file count** — cap on the total number of files included per send.
- **Extra exclusion patterns** — additional glob patterns (on top of built-in exclusions and `.gitignore` rules) used to filter out files from project context.

### Tab 5 — System Prompts

Manage reusable system prompts. Selecting a prompt from the dropdown immediately opens it for editing. The **💾 Save prompt** button activates only when the title or content has been modified. Use **+ New** to create a prompt and **Delete** to remove the currently selected one.

### Tab 6 — Commands

Define slash-command aliases for the chat input field. Type `/` in the input box to open the command picker dropdown and select a command — it is inserted as a short token (e.g. `/tests`) that expands to its full prompt text before being sent to the LLM. Built-in plugin commands appear at the bottom of the picker with an ⚡ prefix and blue-purple colour.

**Built-in commands (read-only)** — shown in a group box at the top of the tab. These are provided by the plugin and cannot be edited or deleted:

| Command | Visible when |
|---|---|
| `/compact` | Compaction enabled + LLM Summary strategy + Full autonomous mode + Project Context off |
| `/clear` | Always |

**User-defined commands** — selecting a command from the list immediately opens it for editing. The **Save command** button activates only when the name or prompt has been changed.

- **+ New** — create a new command (name ≥ 2 characters, no leading `/`; built-in names are reserved)
- **Delete** — remove the currently selected command
- **Restore built-in defaults** — resets the 5 default commands (`/tests`, `/simplify`, `/fix`, `/explain`, `/doc`) to their default prompts without affecting user-defined commands

Commands are stored in `~/.spyder_ai_chat/commands.json`.

### Tab 7 — Auto-complete

Configure AI-powered fill-in-middle (FIM) ghost-text completions in the Spyder code editor. Auto-complete is **disabled by default** and requires explicit setup.

**Setup steps:**

1. Check **Enable AI auto-completion in the editor**.
2. Select a **Provider** and enter the **API URL** (pre-filled for known providers).
3. Click **Load Models** — the plugin fetches the model list and probes which FIM backends the endpoint supports.
4. Choose a **Model** and **Backend type** from the populated dropdowns.

**Backend types** (probed automatically, working ones shown first):

| Backend | Endpoint | Notes |
|---|---|---|
| Ollama /api/generate | `/api/generate` | Native FIM — best choice for Ollama |
| OpenAI-compat /v1/completions | `/v1/completions` | Legacy completions — LM Studio, vLLM |
| Codestral /v1/fim/completions | `/v1/fim/completions` | Mistral / Codestral native FIM |
| Chat completions | `/v1/chat/completions` | Prompt-injection fallback — any provider |

**Model Parameters:** max tokens, temperature, context window before/after cursor.

**Trigger modes:**
- *Auto* — completion fires after a configurable debounce delay (default 600 ms)
- *After new line only* — fires only when a newline is typed
- *Manual only* — press **Alt+\\** to request a completion

Ghost text appears in grey after the cursor. Press **Tab** to accept, **Escape** to dismiss.

### Tab 8 — Agentic

Enable **Agentic mode** to let the LLM take direct actions using special code fences. Each action is shown as an action block in the chat — the LLM never executes anything without your confirmation.

**Master switch** — enable or disable agentic mode globally.

**Autonomous Mode** — three mutually-exclusive radio buttons control how actions are confirmed and whether results are forwarded to the LLM. Click the **ℹ** button next to the label to view the full behaviour-matrix popup.

| Mode | Confirmation | Results forwarded to LLM |
|---|---|---|
| **Manual** | Batch dialog for all actions | Read/ls/grep + git: per-block panel → you decide · Other modifying (file/patch/delete/rename/install): auto-sent ✓ |
| **Semi** | Batch dialog for all actions | ✓ Always auto-sent |
| **Full (confirm modifying)** | Reads: silent · Modifying: confirm dialog | ✓ Always auto-sent |
| **Full (silent all)** | No confirmation for any action | ✓ Always auto-sent |

Sub-option for Full mode: **"Confirm only modifying actions"** (default ON) — when checked, read/ls/grep fences run silently while file/patch/run/install/git fences still go through the confirm dialog.

**Allow action types** — enable or disable each action type independently:

| Action | Fence syntax | Default |
|---|---|---|
| Create / overwrite file | `` ```file:path/to/file.py `` | On |
| Run in IPython console | `` ```run:python `` | On |
| Install package | `` ```install:pip `` | Off |
| Apply unified diff patch | `` ```patch:path/to/file.py `` | On |
| Run git command | `` ```run:git `` | On |

Disabled action types fall back to plain code block rendering so their content is still visible.

**Default base path** — the root directory used to resolve relative file paths in `file:` and `patch:` fences. Defaults to the active Spyder project root, then the user home directory.

In **Semi mode** the typical git commit workflow collapses to **two clicks**: the git bar **Commit** button and **Run selected** in the batch dialog. The LLM then receives the commit output and confirms the result.

**Prompt template** — customise the agentic system prompt injected when agentic mode is enabled. Pre-filled with the built-in default. Use **Reset to default** to restore the original text.

**Action block colours:**
- 🔵 Blue — create new file
- 🟡 Amber — overwrite existing file
- 🟢 Green — run in console / apply patch
- 🩵 Teal — install package
- 🟠 Orange — run git command

After execution the action button is replaced by a **✓ Done** badge. Hover the badge to reveal **↺ Re-run**. Execution state is persisted in the chat history and restored on reload.

**Agentic output messages** — user messages generated automatically by the plugin (git bar prompts, auto-sent execution results) are displayed as a collapsed **⚙ Agentic output** block in the chat. Click the header to expand.

---

## Usage

### Sending messages

1. Type your message in the input box at the bottom.
2. Press **Ctrl+Enter** or click **Send**.
3. The assistant's reply streams in above in real time.
4. Click **Stop** to cancel a reply mid-stream.

### Inference parameters

Click the **inference params bar** (the thin bar above the system prompts row) to open the per-chat parameters popup. Only the parameters supported by the selected provider are shown. Parameters set here override the provider's defaults for this chat session. When active, the bar turns amber and shows a summary of the values set. Starting a new chat resets parameters to defaults.

### Model selection

Click the model name button at the top of the pane to open the model dropdown.
Click **⟳** to refresh the model list from the API.

### System prompt

Type a system prompt in the field above the input box, or select a saved prompt from the **System prompts:** dropdown. Click **↓📋 Copy and edit** to copy a saved prompt into the editable field for customisation.

### Adding file context

Right-click in any **editor tab** to access the **AI Chat** submenu, or use the keyboard shortcuts:

- **Add file to context** — attaches the current file's full content. Shortcut: **Ctrl+Shift+A**
- **Add selection to context** — attaches the currently highlighted text. Shortcut: **Ctrl+Shift+Q**

Right-click in the **IPython console** to access the same **AI Chat** submenu:

- **Add console content to context** — attaches the full console output text.
- **Add selection to context** — attaches the currently selected console text.

Context tags appear above the input box and can be dismissed individually before sending. **Editor attachments** are shown with a blue tag; **console attachments** are shown with a teal-green tag.

### Chat history

Click the checklist icon (🗒) in the toolbar to open the chat history popup.

- **Collection selector** — choose a named collection or *Default* to browse chats from that collection only; choose **⊕ All Collections** to search and list chats from every collection.
- **⚙ (gear) button** — opens the Collection Manager dialog to create, rename, and delete collections, and to move chats between them.
- **Search field** — type any text to instantly filter chats; searches both the title preview and the full message content of every saved chat.
- **Click an entry** to load that chat.
- **✕** — delete a chat (3-second countdown with Cancel).
- **Right-click an entry** — **Move to →** submenu lets you move that chat to any other collection.
- **🗑 Delete all** — hover for 1 second to unlock, then a 3-second countdown before deletion; deletes all chats in the currently selected collection only.
- The **active chat** is highlighted green.

Chats are saved to `~/.spyder_ai_chat/chats/`. Named collections are subdirectories (e.g. `chats/Work/`).

### Project context

Click the **📁 Proj. Context ○** toggle button in the chat bar to enable project-wide context.

- A folder-selection dialog opens showing all top-level project folders with file counts and an estimated token count. Check the folders to include and click **Enable project context**.
- The badge changes to **📁 Proj. Context ●** (amber) and appears in the attachment bar for every message.
- **First message** — all selected files are sent in full. Open files with unsaved edits use the live editor buffer. New unsaved files (not yet on disk) are always included automatically.
- **Subsequent messages** — only files that changed since the last send are appended as a delta block. Unchanged files are already in the LLM's conversation history and are not re-sent.
- **File change detection** — a file watcher monitors the project directory. The badge shows a changed-file count (e.g. `· 3 changed ⚠`) before you send.
- **Disabling** — click the **●** toggle again; a confirmation dialog warns that context will be detached from the chat.
- **Whole-file attachments** are blocked while project context is ON to avoid duplication. Editor selections and IPython console attachments remain available.
- Configure max file size, max file count, and extra exclusion patterns in **Settings → 📁 Context**.

### AI auto-complete (FIM ghost text)

Once configured in **Settings → Auto-complete**, ghost-text suggestions appear automatically while typing in the editor.

- **Tab** — accept the full suggestion
- **Escape** — dismiss the suggestion
- **Alt+\\** — manually request a completion (when trigger mode is *Manual only*)

The completion uses the code before and after the cursor as context (configurable character limits).

### Markdown rendering

- **Headings** H1–H3 with scaled sizes
- **Bold**, *italic*, ***bold+italic***, ~~strikethrough~~, `inline code`
- Bullet and numbered lists with **arbitrary nesting** — cycling symbols (`•`, `◦`, `▪`, `▸`)
- Blockquotes with blue left border
- Fenced code blocks with language label, **Copy to editor** button, and **horizontal scrollbar** for long lines
- Tables with header row and alternating row shading
- Clickable hyperlinks
- `<think>...</think>` blocks rendered as a collapsible **Thinking** box with scrollbar — works with DeepSeek-R1, QwQ, Qwen-thinking variants

### Ollama quick-start

```bash
ollama serve          # starts the server on port 11434
ollama pull llama3    # download a model
```

In **Settings → Connection** select **Ollama (local)**. URL is pre-filled; leave the API key blank.

---

## Data storage

All plugin data is stored under `~/.spyder_ai_chat/`:

| Path | Contents |
|---|---|
| `state.json` | Provider type, API URL, selected model, model list cache, editor font sizes, history settings, FIM configuration, active collection |
| `chats/` | One JSON file per saved chat session (Default collection) |
| `chats/<CollectionName>/` | Chats belonging to a named collection |
| `system_prompts.json` | Saved system prompts library |
| `commands.json` | Slash-command aliases |

---

## Project structure

```
spyder_ai_chat/
├── pyproject.toml               # Build config, version 0.8.8, author, license
├── README.md                    # This file
├── README_PYPI.md               # PyPI landing page description
├── LICENSE                      # MIT
└── spyder_ai_chat/
    ├── __init__.py              # Package init
    ├── plugin.py                # SpyderDockablePlugin subclass —
    │                            #   Spyder integration, editor + IPython
    │                            #   console context menu injection,
    │                            #   FIM ghost-text wiring
    ├── confpage.py              # Preferences page (reserved for future use)
    ├── fim/
    │   ├── __init__.py
    │   ├── client.py            # HTTP FIM client:
    │   │                        #   multi-backend request/response handling
    │   │                        #   (Ollama, OpenAI-compat, Codestral, chat fallback)
    │   ├── config.py            # FIM configuration dataclass:
    │   │                        #   provider, URL, API key, model, backend type,
    │   │                        #   max tokens, temperature, context window,
    │   │                        #   trigger mode, debounce delay
    │   ├── ghost_text.py        # Ghost-text rendering:
    │   │                        #   inline grey suggestion overlay in the editor,
    │   │                        #   Tab to accept, Escape to dismiss,
    │   │                        #   cursor-offset fix for \r\n line endings
    │   ├── provider.py          # FIM completion provider:
    │   │                        #   AiFimProvider (Spyder completions API),
    │   │                        #   debounce timer, trigger-mode dispatcher,
    │   │                        #   Escape ShortcutOverride intercept
    │   └── widgets/
    │       ├── __init__.py
    │       └── status.py        # FIM status-bar widget:
    │                            #   shows active model / provider in the editor status bar
    └── widgets/
        ├── __init__.py
        ├── chat_widget.py          # Main chat panel UI:
        │                           #   streaming API worker, model popup,
        │                           #   chat history popup, inference params popup,
        │                           #   file context bar, system prompt selector,
        │                           #   bottom panel layout, state persistence
        ├── chat_history_manager.py # File-per-chat JSON storage:
        │                           #   save / load / delete / list chats,
        │                           #   collection directory helpers
        ├── collection_manager.py   # ChatCollectionManagerDialog:
        │                           #   create / rename / delete collections,
        │                           #   move chats between collections
        ├── markdown_renderer.py    # Markdown → Qt widgets renderer:
        │                           #   headings, paragraphs, recursive nested lists,
        │                           #   tables, code blocks (QPlainTextEdit + h-scroll),
        │                           #   blockquotes, think blocks (scrollable),
        │                           #   inline formatting, configurable font sizes
        ├── settings_dialog.py      # Tabbed settings dialog:
        │                           #   provider registry (12 providers + param defs),
        │                           #   Connection tab (dynamic form + Test Connection),
        │                           #   Dialogs font sizes, History options,
        │                           #   System Prompts & Commands (auto-edit on select,
        │                           #   dirty-save tracking), Auto-complete FIM tab
        ├── system_prompts.py       # Saved system prompts CRUD:
        │                           #   load / save / new / update / delete,
        │                           #   persisted to ~/.spyder_ai_chat/system_prompts.json
        ├── commands.py             # Slash-command definitions:
        │                           #   load / save / defaults,
        │                           #   persisted to ~/.spyder_ai_chat/commands.json
        └── agentic_actions.py      # Agentic action execution:
                                    #   execute_create_file, execute_patch_file,
                                    #   _apply_unified_diff, run_git_command,
                                    #   show_confirm_dialog, show_batch_confirm_dialog,
                                    #   AGENTIC_SYSTEM_PROMPT constant
```

---

## Requirements

- Python ≥ 3.9
- Spyder ≥ 6.0
- No extra Python packages — uses only `urllib` from the standard library for HTTP and Qt (already bundled with Spyder) for the UI.

---

## Changelog

### 0.8.8
- **Collapsible agentic action pairs** — completed assistant+agentic-output message pairs are now automatically collapsed into the assistant title row after rendering; the label shows **"Agentic: Read file, Git command ▶"** (dark-yellow, with action names de-duplicated); clicking it expands both inner blocks and changes the arrow to **▼**; clicking again collapses; delete buttons are hidden while collapsed and restored on expand; consecutive runs of 2+ agentic pairs are grouped under a single label with repeat counts (e.g. **"Agentic: Git command ×2 ▶"**); applies to both history loads and live streaming responses; `_blocks` is never modified so the `block_idx → msg_idx` mapping used by delete remains correct
- **Agentic collapse — live grouping shake fixed** — when a second consecutive agentic pair arrived during live streaming, the chat briefly "shook" (content flashed visible then re-collapsed) as the old undo+redo approach removed and re-inserted the summary label; replaced with a surgical extension strategy: on each `_wrap_agentic_pairs()` call the existing collapse group is grown in-place by appending new widgets to the same mutable list already captured by the toggle closure, and the summary label text is updated via `setText()` instead of being removed and re-created; the toggle closure automatically covers the new widgets because it holds a reference to the shared list; zero visual artifact, no expand/contract cycle, no floating label
- **Fence parser — infinite loop on spaces in fence tag fixed** — any action fence whose tag contained a space (e.g. `` ```grep:SHOW TABLES ``, `` ```file:path/with spaces.py ``) caused `parse_blocks()` to enter an infinite loop, making Spyder completely unresponsive; root cause: the fence-opening regex `\S*` stopped at the first space so the line failed to match the fence branch; the paragraph collector then immediately broke on its own `` ^``` `` guard without advancing `i`, sending the outer loop back to the same line forever; fixed by changing the regex capture group from `\S*` to `(\S[^\n]*?|)` so the full tag (including embedded spaces) is captured as long as it starts with a non-whitespace character; a second defensive `elif i += 1` guard was added after the paragraph collector so that any `` ``` ``-starting line that still fails the fence regex (e.g. `` ``` lang `` with a leading space between the backticks and the lang) advances `i` rather than looping
- **Blockquote rendering fix** — the `>` markdown blockquote no longer shows a doubled vertical line on the left; root cause was Qt's built-in frame border engine adding a second line when `border-left` was set on a `QFrame`; fixed by switching to a plain `QWidget` with a separate 3 px wide coloured child widget as the accent bar; nested fenced code blocks inside blockquotes now render correctly as full syntax-highlighted code block widgets instead of plain text
- **Plugin logo in Settings dialog** — the plugin logo is now displayed at the bottom of the tab-bar column in the Settings dialog; it is embedded in the package under `spyder_ai_chat/resources/` (declared as package data in `pyproject.toml`) so it is available after `pip install` without any extra files; position is recomputed on every resize via `resizeEvent`
- **Git bar disabled by default** — the git status bar is now off by default for new installs; users enable it explicitly once they have confirmed git is available on their system
- **Git availability check on enable** — when the "Show Git status bar" checkbox is ticked in Settings → ⎇ Git bar, the plugin immediately checks git availability via `shutil.which("git")` (a pure PATH lookup — no subprocess, no blocking, no console flash); a green **"✓ git found in PATH"** label appears next to the checkbox if git is found; if git is absent a red **"⚠ git not found in PATH — bar will not work"** warning is shown and the checkbox is automatically unchecked; the check also runs at dialog open time if the setting was already enabled

### 0.8.7
- **Settings — light theme support** — resolved multiple elements that were invisible or showed a black box when Spyder's light UI theme was active: Context tab warning boxes (LLM Project Context and LLM Summary compaction), Agentic tab full-autonomy warning, Commands tab built-in commands group box, Connection tab title label, autonomous mode behaviour matrix popup (all colours now theme-conditional), and agentic system prompt preview textarea; all theme-adaptive styling uses a `_is_dialog_dark()` helper that reads Spyder's `appearance/ui_theme` setting with a QPalette luminance fallback
- **Table rendering — height fix** — LLM table responses no longer stretch to fill the full chat window height when no vertical scrollbar is visible; root cause: `QTextBrowser.showEvent` fired before the viewport had a valid width, causing `setTextWidth(0)` which produced an enormous document height; fixed by guarding against `w ≤ 0` before calling `setTextWidth` and changing the vertical size policy from `Expanding` to `Preferred`
- **Manual mode — inspection output panel** — executing a `read:`/`ls:`/`grep:` fence in Manual autonomous mode via the batch confirmation dialog now correctly shows the per-block output panel with **"📤 Send to LLM"** and **"✕ Dismiss"** buttons; previously the result was silently discarded because the `_on_execute()` path was never reached in the batch execution route
- **Manual mode — git output panel** — confirming a `run:git` fence in Manual mode now shows the git output panel with **"📤 Send to LLM"** and **"✕ Dismiss"** buttons; previously git output was auto-sent to the LLM without user control regardless of mode
- **Manual mode — modifying action results auto-sent** — results from `file:`, `patch:`, `delete:`, `rename:`, and `install:` fences confirmed in Manual mode are now automatically forwarded to the LLM as brief confirmations so it knows what completed; only `read:`/`ls:`/`grep:` and `run:git` results remain under user control via the output panel
- **"📤 Send to LLM" on git panel — sends immediately** — clicking the button on a git output panel previously only added an attachment tag to the context bar without triggering a message send; it now calls `auto_send_fn` which adds the tag and immediately fires `_send()`, consistent with the inspection panel behaviour
- **Autonomous mode behaviour matrix — git row added** — git now has its own row in the matrix popup (Manual: "panel → user decides"; Semi/Full: "auto-sent ✓"); previously git was incorrectly grouped under the Modifying row showing "auto-sent ✓" for Manual mode; legend updated accordingly
- **Git output panel — text always visible** — the text area no longer collapses to show only a scrollbar when the command output contains a long line (e.g. the LF→CRLF warning from `git add`); changed from `NoWrap` to `WidgetWidth` wrap mode so long lines fold instead of triggering a horizontal scrollbar that consumed the full widget height; added a minimum height floor of 52 px to guard against near-zero font metrics on hidden widgets
- **Dead code removed** — four legacy `inject_*_output_fn` closures and their env-dict keys have been removed; they were superseded by `auto_send_fn` across all output panel send paths
- **Editor keyboard shortcuts** — two keyboard shortcuts are now available in the Spyder code editor: **Ctrl+Shift+A** adds the current file to the AI Chat context; **Ctrl+Shift+Q** adds the current text selection to the context; both shortcuts are scoped to the editor widget so they do not interfere with the rest of Spyder; the key bindings are also shown as hints in the right-click **AI Chat** submenu

### 0.8.6
- **Dynamic agentic system prompt** — the agentic system prompt injected into each chat is now assembled at send time from only the fence types that are enabled in Settings → 🤖 Agentic; a user who enables only `patch:` and `read:` sees a prompt that describes only those two fences — the LLM is never told about fences it cannot use; previously the full 12-fence prompt was always sent regardless of which fences were enabled
- **Mode-aware agentic prompt wording** — the injected system prompt now adapts its phrasing to the selected autonomous mode; the preamble correctly describes whether the user must confirm actions via a dialog, whether results are auto-forwarded, or whether execution is fully silent; git output, delete/rename confirmation text, and the inspection-fence discipline paragraph also vary by mode
- **Missing delete / rename fences in system prompt — fixed** — `delete:`, `delete_dir:`, `rename:`, and `rename_dir:` fences were fully implemented but never mentioned in the agentic system prompt, so the LLM did not know they were available; they are now included as conditional sections (shown only when the respective fence is enabled in Settings)
- **Settings: read-only agentic prompt preview** — the editable prompt textarea in Settings → 🤖 Agentic is replaced by a collapsible read-only preview that shows the exact system prompt that will be injected for the current combination of enabled fences and selected autonomous mode; the preview updates live as any checkbox or mode radio button is toggled; the prompt_template field is removed from saved state
- **Agentic action widget — no blank body for delete / rename fences** — `delete:`, `delete_dir:`, `rename:`, and `rename_dir:` action blocks in the chat no longer show an empty text area below the header; the target path (and destination for rename) is fully described in the header row, so rendering an empty content body was redundant; the fix aligns these fences with `git`, `read`, `ls`, and `grep` which already suppressed the body area
- **Chat history paging** — chats longer than 120 messages are now split into pages; a centered navigation bar (`<<` / `<` / five numbered page buttons / `>` / `>>`) appears below the chat area when paging is active; the current page button is highlighted in blue; opening a saved long chat displays the last (newest) page with the scroll position anchored to the bottom; navigating to any earlier page scrolls to the top; page navigation reuses the batched-load pipeline with a "Page N loading… N%" progress overlay so the UI stays responsive; page navigation buttons are disabled during active streaming and re-enabled when the response finishes; chats with 120 or fewer messages are completely unaffected — the page bar stays hidden
- **Incremental chat history loading** — history loading is now split into batches of 12 messages with an event-loop yield between each batch, so the application remains interactive (scrollable, closable, resizable) while a large chat loads; a "Loading chat… N%" progress overlay tracks progress and disappears when the last batch is rendered; before this change the UI froze completely for the entire load duration
- **Chat scroll height — long-chat sizeHint fix** — loading a saved chat with more than 120 messages no longer produces large blank space below the last message; root cause was Qt's internal sizeHint cache becoming stale after rendering many word-wrapped labels in a single layout pass; paging caps the rendered widget count to 120 per page (20 full batches of 6), which stays within the range where the cache remains reliable
- **Patch diff line numbers** — `patch:` action blocks in the chat window, the single-action confirmation dialog, and the batch confirmation dialog all now show line numbers on the left border of the diff view; two gutter columns display old-file line number (left) and new-file line number (right), both parsed from `@@` hunk headers so they reflect real file positions rather than diff-relative offsets; removed lines show only the old-file number, added lines show only the new-file number, context lines show both; gutter width auto-sizes to the widest line number in the diff; `@@` hunk separator rows now display the full header text (`@@ -N,M +P,Q @@`) instead of the former `──────────────` placeholder
- **Patch application — context verification** — `_apply_unified_diff` now verifies that the file content at the line-number-computed position matches the expected hunk context before applying; previously each hunk was written blindly, meaning stale LLM-generated line numbers could silently corrupt lines far from the intended edit
- **Patch application — fuzzy fallback with offset recalibration** — when context verification fails (stale line numbers), the engine falls back to a content-based fuzzy search; when a fuzzy match is found at a different position, the running offset is recalibrated so all subsequent hunks in the same diff are also placed correctly; hunks that cannot be located by either strategy are skipped rather than misapplied
- **Patch application — Python indentation / whitespace preservation** — when the fuzzy path is taken, context lines (unchanged lines that bracket the actual edit) are now sourced from the FILE's original content verbatim instead of from the diff; this prevents the LLM's slightly-wrong context lines (e.g. 3 spaces instead of 4, or missing trailing whitespace) from overwriting correct indentation — especially important for Python code where indentation is semantically significant; added lines continue to use the diff content as the LLM set their indentation intentionally
- **Chat scroll height — bug fix** — fixed ~950 px of empty space appearing at the bottom of the chat pane after a streaming response finished; root cause: `QScrollArea` processes `updateGeometry()` asynchronously via `QEvent::LayoutRequest`, so the content widget retained its old inflated height for one event-loop pass after the streaming label was removed; fix: synchronously resize `_ChatHistory` to the correct height immediately after layout invalidation; also improved the `_scroll_to_bottom` retry condition to distinguish genuinely-unreachable scroll targets from layout-not-yet-propagated cases

### 0.8.5
- **Context History Compaction** — new configurable feature in Settings → 📁 Context that limits how much history is forwarded to the LLM on each turn without ever deleting messages from the local chat log:
  - **Cut-off** strategy: oldest user+assistant pairs are silently dropped from the LLM payload when estimated token usage exceeds the configured threshold (%)
  - **LLM summary** strategy: in Full autonomous mode, a summary request is automatically sent when the threshold is reached; the LLM's response is stored as a collapsible 📦 compaction block in the chat; all subsequent sends include only messages after that block, with the summary injected as a system context note
  - Per-provider/model token limit table with provider dropdown and editable model combo (pre-populated with the live model list when provider matches the active one); configurable default fallback limit and trigger threshold
  - Compaction is automatically disabled while Project Context is active
- **Built-in commands** — new plugin-defined command category (not user-editable, not stored in `commands.json`); shown with ⚡ prefix and blue-purple colour in a dedicated "── Built-in ──" section of the slash-command picker dropdown; displayed read-only in a group box at the top of the Commands settings tab; built-in names are protected from user collision in the save validator
- **`/compact` built-in command** — manually triggers LLM summary compaction of the chat history; visible in the dropdown only when ALL four conditions are met simultaneously: Context History Compaction enabled, strategy = LLM Summary, autonomous mode = Full, and Project Context not active for the current chat; ignores the token threshold but re-validates all other guards before firing; selecting it removes the `/` from the input field and fires the compaction silently (no user message is added to the chat)
- **Context size estimate in params bar** — always-visible `~X.Xk / Yk (Z%)` button on the right side of the inference params bar; colour-coded: gray (normal), amber (near compaction threshold), red (over limit); hovering shows a dark floating popup with a progress bar and per-category token breakdown (history messages, system prompt, context files, compaction buffer, total, free space) plus the active compaction strategy and threshold; refreshes on every send, LLM response completion, and chat switch
- **Inspection fence output panel** — executing a `read:`/`ls:`/`grep:` fence in manual mode (auto-send OFF) now shows a scrollable output panel with **"📤 Send to LLM"** and **"✕ Dismiss"** buttons; previously the result was silently discarded when the user clicked Execute
- **Confirm dialog for inspection fences** — the confirmation dialog for `read:`/`ls:`/`grep:` fences now shows the correct icon, a human-readable label ("Read File" / "List Directory" / "Search in Files"), and a styled detail block (file path with optional line range, directory path, or pattern + scope); previously showed "? read" with an empty preview body
- **Project root in system prompt** — when a Spyder project is open the absolute project root path is automatically appended to the system prompt so the LLM uses it as the base directory for all file operations even when Project Context is disabled; prevents the LLM from defaulting to the filesystem root
- **Agentic output visual** — the collapsed "⚙ Agentic output" user-message frame now has a straight blue left border (`#569cd6`, `border-radius: 0`) matching the style of regular user message bubbles
- **Attachment content tooltip** — hovering over any locked attachment badge in a sent user message shows the first 25 lines of the attachment content as a tooltip; a "… (N more lines)" footer appears when the content is longer
- **Regenerate after service error — bug fix** — fixed two root causes of the LLM not receiving agentic action output when regenerating after a failed response: (1) `_on_regenerate` now correctly marks already-executed fence indices so they are excluded from `_exec_registry` during the history rebuild; (2) `read:`/`ls:`/`grep:` results now use `source="result"` (was `"file"`) so they are never silently dropped by `add_file_context_content` when Project Context is enabled
- **Context size estimate refresh on chat switch — bug fix** — the context size estimate in the params bar now correctly recalculates after loading a saved chat; previously `_update_ctx_size_label()` was called before messages were restored, so the counter always showed the empty-history value until the next LLM call
- **"Send to LLM" button** — the "📎 Add to chat" label on the inspection output panel and git output panel renamed to "📤 Send to LLM"
- **Settings: ⎇ Git bar tab** — git status bar settings moved from the Context tab to a dedicated "⎇ Git bar" tab placed between History and Context
- **Settings window height** — minimum height raised from 520 px to 770 px
- **Context tab: Project Context warning** — amber warning banner added inside the "📁 LLM Project Context" settings group and in the folder-selection dialog, advising users to prefer agentic read/ls/grep actions for token efficiency
- **Agentic warning colour** — the "Full autonomous mode" warning box in Settings → 🤖 Agentic now uses amber styling (matching the Project Context warning) instead of red
- **"− Remove row" button fix** — the button in the Compaction token limits table was clipping the last letter; width corrected
- **`/clear` built-in command** — clears all messages in the current conversation while keeping every setting (model, system prompt, inference parameters, project context, collection); the conversation is unconditionally saved to history before wiping regardless of the autosave setting; always visible in the slash-command picker for all chats; does not add a user message to the chat; replaces the former toolbar 🗑 button
- **Read fence batch grouping** — two or more consecutive `read:`/`ls:`/`grep:` action blocks from the same LLM response are automatically collapsed into a single collapsible summary block: ▶/▼ toggle in the header, scrollable path list, ✓ Done badge in the header row; individual button rows are hidden; applies to both live streaming responses and history reloads
- **Read fence auto-batching in off mode** — when autonomous mode is Off, all `read:`/`ls:`/`grep:` fences in a response are collected into a single batch execution (matching the behaviour of Semi/Full modes); previously each fence required a separate manual Execute click
- **Agentic output hover popup** — the "⚙ Agentic output" label now triggers a custom scrollable floating popup on hover instead of the system QToolTip; dark blue (`#0d1a2e`) background, 420 px max height with vertical scroll, 200 ms hide grace timer; tooltip fires only from the label text, not the full header row
- **Context size refresh on delete** — the `~X.Xk / Yk (Z%)` token counter now updates immediately after deleting any exchange; previously it stayed stale until the next LLM send
- **`/clear` history save fix** — the clear action now saves to history unconditionally before wiping; previously the save was gated on the `save_on_new` setting, meaning an autosaved file could remain on disk with old messages and reload them when navigated to from the history popup
- **"Off" autonomous mode renamed to "Manual"** — the former Off mode now shows a batch confirmation dialog for ALL action types (read/ls/grep and modifying alike), identical to Semi mode, but results are never auto-sent to the LLM; the key distinction between Manual and Semi is purely the auto-send step; the internal stored value `"off"` is unchanged for backward compatibility
- **Autonomous mode behaviour matrix popup** — a small **ℹ** button next to the "Autonomous Mode:" label in Settings → 🤖 Agentic opens a dialog with a colour-coded table showing confirmation style and auto-send behaviour for every action type across all four mode variants (Manual, Semi, Full-confirm, Full-silent)
- **Removed "Auto-send individual Execute results" checkbox** — the standalone checkbox that was only enabled in Manual mode has been removed; it was redundant (Manual+auto-send is functionally identical to Semi) and misleading given the new batch-dialog behaviour
- **Agentic mode enabled by default** — new installs start with agentic mode on; context history compaction is also on by default with the Cut-off strategy
- **Stop-before-first-token Regenerate fix** — clicking Regenerate after stopping a response before any tokens arrived now correctly re-sends the last user message; previously `_on_regenerate` bailed out immediately because the last stored message was the user's auto-send (not an assistant reply), and the Regenerate button itself was not repositioned after the empty streaming block was removed
- **Console output shown as Agentic output block** — auto-sent console execution results are now rendered as the collapsed blue **⚙ Agentic output** frame (matching other agentic auto-sends) instead of a plain "You:" user bubble; root cause was a missing `_pending_agentic_response = True` flag in the async console output callback
- **Batch confirm dialog patch preview fix** — opening the batch confirmation dialog when it contained a `patch:` action caused a `TypeError: _diff_to_html() got an unexpected keyword argument 'context_lines'`; fixed by passing `font_size=9` as a positional argument, matching the function signature
- **Settings version label fix** — the plugin version label in the bottom-left of the settings dialog was clipped to "Ch" because `tabBar().sizeHint()` was called while `WA_DontShowOnScreen` was active (zero layout size); replaced `setFixedWidth(sizeHint)` with a natural-width label + `addStretch()` between label and buttons

### 0.8.4
- **Full autonomous mode** — new third execution mode in `Settings → 🤖 Agentic`; the LLM's requested actions are executed immediately without any confirmation dialog; sub-option "Confirm only modifying actions" (default ON) still shows the batch dialog for file/patch/run/install/git actions while silently auto-executing read-only inspection fences (read/ls/grep)
- **Autonomous mode redesign** — the former "Semi-autonomous mode" label + two checkboxes are replaced by a proper **Autonomous Mode** section with three mutually-exclusive radio buttons: Off, Auto-show batch confirmation (semi — default), and Full autonomous; "Auto-send execution results" is a standalone option below the radios, free to toggle in Off mode, forced ON in Semi/Full
- **On-demand file inspection fences** — three new agentic fence types the LLM can use to inspect project files without requiring full project context: `read:path/to/file.py` (full or line-range read), `ls:some/dir/` (directory listing with line counts for ≤50 entries), `grep:pattern` / `grep:pattern:src/` (regex search across files with file:line output, capped at 200 results)
- **Read line-range syntax** — `read:path/to/file.py:100-150` reads only lines 100–150; header always shows total line count so the LLM knows the file size; `read:file.py:1-1` is a cheap way to learn total size before reading a large file
- **Inspection error forwarding** — when a `read:`/`ls:`/`grep:` fence fails (file not found, invalid regex, etc.) the error is now forwarded to the LLM so it can react correctly instead of hallucinating based on missing output
- **Inspection fence discipline in system prompt** — the agentic system prompt now explicitly instructs the LLM to end its response immediately after outputting a `read:`/`ls:`/`grep:` fence and not speculate about the contents before receiving real results, preventing duplicate responses
- **Git bar refresh timer configurable** — new "Refresh interval" spinbox in `Settings → 📁 Context → Git Status Bar` (default 10 s, range 5–300 s); the timer catches working-tree edits that don't touch `.git/HEAD` or `.git/index`
- **Git bar counts untracked files** — switched from `git diff --shortstat HEAD` (tracked only) to `git status --porcelain`; new/untracked files now appear in the diff stats immediately without staging
- **All git outputs forwarded in batch** — fixed a bug where only the first `run:git` command's output was sent to the LLM when multiple git commands were batched; root cause was (1) `target` always empty for git blocks (command lives in `content`), (2) duplicate tag names silently dropped by `add_file_context_content`
- **Settings tabs vertical with horizontal labels** — the settings dialog tab bar is now on the left side with compact horizontal text labels; tab height is font-height + 24 px padding; version label moved to bottom-left corner centred under the tab column
- **Context tab grouped** — the Context settings tab is split into two `QGroupBox` sections: "📁 LLM Project Context" and "⎇ Git Status Bar"
- **Agentic output tooltip** — hovering over an ⚙ Agentic output block shows the full message text and each attachment's content in a tooltip; clicking no longer expands the block (content is attachment data not meant for inline display)
- **Re-run disabled for inspection fences** — the ✓ Done badge on `read:`/`ls:`/`grep:` blocks is a static indicator with no hover animation and no re-run on click, since re-running an inspection doesn't make sense mid-conversation
- **"Copy to editor" button removed** — the per-response "📋 Copy to editor" button that appeared after plain-text LLM responses has been removed

### 0.8.3
- **Batch confirmation dialog** — all agentic action blocks produced by a single LLM response are grouped into one scrollable dialog; each row shows a user-friendly verb + target with a per-action include/exclude checkbox; "Run selected" executes only the checked items in block order; "Cancel" leaves all Execute buttons available as before
- **Auto-show confirmation** (`Settings → 🤖 Agentic → Semi-autonomous mode`) — when enabled the batch dialog appears automatically after each LLM response that contains action blocks, without requiring the user to click individual Execute buttons; requires at least one uncompleted action block in the response
- **Auto-send execution results** — after actions complete, each result is injected as a context tag and a follow-up is automatically sent to the LLM so it can confirm success or react to errors; always enabled when Auto-show confirmation is on; available independently for manual Execute clicks when Auto-show confirmation is off
- **Collapsible agentic output messages** — user messages generated by the plugin (auto-sent results, git action prompts from the git bar) are wrapped in a collapsed **⚙ Agentic output** frame in the chat view; click to expand; stored in JSON as `"agentic_response": true`
- **Sequential git execution in batch mode** — when a batch contains multiple `run:git` commands (e.g. `git add -A` then `git commit`), each command waits for the previous to finish before starting, preventing race conditions
- **Auto-dismiss git output panel** — when auto-send is enabled, the inline output panel that would normally appear after a git command is suppressed; the ✓ Done badge is shown instead and the output travels to the LLM automatically; the panel still appears in manual mode
- **Settings constraint: auto-confirm implies auto-send** — enabling "Auto-show batch confirmation" forces "Auto-send execution results" on and grays it out; the two options can be toggled independently only when auto-confirm is off
- **No console popup windows on Windows** — git subprocess calls now use `CREATE_NO_WINDOW` so no terminal flickers on screen during git operations

### 0.8.2
- **Git Status Bar** — a compact bar below the context tag bar shows the current branch name (`⎇ branch`), uncommitted diff stats (`+N −N in N files`), and three action buttons that send a pre-filled prompt to the LLM: **Commit** (asks the LLM to suggest a commit message + `run:git commit` fence), **PR desc** (generates a PR description from the current diff), and **Changes** (summarises uncommitted changes); the bar is hidden when no Spyder project is open or the root is not a git repository
- **Git bar auto-refresh** — the bar updates automatically when `.git/HEAD` (branch switch) or `.git/index` (staged changes) is modified, using a non-blocking `QThread` worker; the worker guard prevents overlapping queries
- **Branch-change context injection** — when the active branch changes while a chat has project context enabled, the next delta context update includes the new `Branch:` header so the LLM always knows the current branch
- **Git info in project context** — when the git bar is enabled, `Branch: <name>` and `Uncommitted: <diff_stat>` are injected into the project context header sent with each message (configurable via *"Show git status bar"* in Settings → 📁 Context)
- **`show_git_bar` setting** — new checkbox in Settings → 📁 Context controls both bar visibility and git metadata injection into project context; defaults to enabled

### 0.8.1
- **`run:git` agentic fence** — the LLM can run git commands via `` ```run:git `` fences; each command shows as an orange action block; execution is non-blocking (QThread); output appears inline with **📎 Add to chat** / **✕ Dismiss** buttons; adding output injects an orange attachment tag into the next message; git availability is checked before execution with a friendly error if git is not on PATH
- **Diff syntax highlighting** — `patch:` action blocks render with coloured unified-diff highlighting (`+` lines green, `−` lines red, `@@` dividers) in both the chat block and the confirmation dialog; the internal patch text is always preserved unchanged for correct application
- **Robust patch application** — `_apply_unified_diff` now falls back to fuzzy line-search when the LLM omits line numbers from the `@@` hunk header (bare `@@`), preventing silent no-op patches
- **Agentic system prompt upgrade notice** — removed the hash-based auto-upgrade mechanism; instead shows an amber warning label in Settings → 🤖 Agentic: *"If agentic mode doesn't work properly after a plugin upgrade, reset the agentic system prompt!"*; **Reset to default** button moved to the always-visible header row above the collapsible textarea
- **Agentic `patch:` vs `file:` rule** — the built-in system prompt now includes an explicit rule: use `patch:` to edit existing files, `file:` only for brand-new files; editing/modifying prompts always produce a `patch:` fence
- **Full absolute paths in file attachments** — manually attached files, editor selections, and project context blocks all store and display the full absolute path so the LLM can use them directly in fences
- **Wrapping context bar** — the context tag bar now uses a flow layout that wraps to the next row instead of expanding the plugin window horizontally; project context toggle stays in a fixed right column
- **Always-off project context on new chat** — starting a new chat always disables project context (configurable via the new *"Always disable project context when starting a new chat"* checkbox in Settings → 📁 Context)
- **Clear manual attachments on project context enable** — toggling the project context toggle ON now removes any manually attached files from the context bar (project context replaces them)
- **Live project root for agentic actions** — base directory for file/patch/git actions is now resolved lazily at click time using the live Spyder project root, regardless of whether project context is enabled for the chat; home directory is the last-resort fallback only
- **`.git` metadata files in project context** — `HEAD`, `config`, `COMMIT_EDITMSG` and other readable `.git` files are now correctly collected when project context is active (walk into `.git/` root only; subdirectories like `objects/` and `refs/` are still excluded)
- **Version shown in Settings** — plugin version is now displayed at the bottom of the Settings → Connection tab

### 0.8.0
- **Named chat collections** — organise saved chats into user-defined collections (folders inside `~/.spyder_ai_chat/chats/`); the Default collection at the root is fully backward-compatible with existing chat files
- **Collection selector in history popup** — a "Collection:" dropdown above the search field lets you browse one collection at a time or switch to **⊕ All Collections** to search and list chats across every collection simultaneously
- **Collection Manager dialog** — click the ⚙ gear button next to the selector to open a side-by-side manager: left panel lists collections, right panel shows chats in the selected collection; buttons: **+ New**, **Rename**, **Delete** (with choice to delete chats or move them to another collection), and **Move selected to [combo]** for bulk chat moves
- **Right-click "Move to →"** — context menu on any chat row in the history popup offers a submenu listing all other collections; moving the currently open chat updates the panel's active collection reference live
- **Delete all scoped to current collection** — the "🗑 Delete all" button removes only the chats visible in the selected collection; the button is hidden when "All Collections" mode is active
- **Collection badge in All-Collections view** — chat rows show a `[CollectionName]` badge in the timestamp area when browsing all collections, so the source is always visible
- **Persistent collection state** — the active collection is saved to `state.json` (`current_collection` key) and restored on restart; `last_chat_file` encodes the collection as `"CollectionName/filename.json"` for non-default collections (bare filename = Default, fully backward-compatible)
- **Auto-complete settings fix** — "Context before cursor" QSpinBox range lowered from minimum 100 to 1, fixing a Qt intermediate-validation bug that caused the value to be silently reset to 100 when clicking OK
- **Button icon fixes** — "⚙ Settings" button now uses the Unicode text-variation selector (U+FE0E) to force monochrome rendering on Windows, preventing the coloured emoji appearance at startup

### 0.7.1
- **Project Explorer context menu** — right-click any file (or multi-select files) in the Project Explorer pane to access the **AI Chat** submenu: *Add file to context* for a single file, *Add N files to context* for a multi-selection; directories are silently skipped; the action is automatically disabled when project context is ON (same rule as the editor context menu)
- **Editor context menu fix (Spyder 6.1.4)** — the *AI Chat* submenu in the editor right-click menu disappeared after upgrading to Spyder 6.1.4; fixed by switching from the deprecated `codeeditor.menu` attribute to the new `codeeditor.get_menu('context_menu')` / `get_menu('read_only_menu')` API; both writable and read-only editor tabs are supported; Spyder ≤ 6.1.3 fallback retained
- **Agentic: overwrite header updates live** — after clicking *✓ Create file* the action block header, border, and button immediately switch to the amber *⚠ Overwrite file* state without requiring a chat reload
- **Agentic: patch reloads open file** — after *✎ Apply patch* succeeds, if the patched file is currently open in the editor its buffer is reloaded from disk automatically; files not open are left untouched
- **Agentic: startup chat action blocks fixed** — *Run in console* blocks in the default startup chat now execute correctly on first click; previously they showed *⚠ No console available* until the user switched chats and returned (project context and base path were being resolved after the message loop instead of before)
- **Agentic: overwrite detection on startup fixed** — *Create file* blocks in a startup chat now correctly show *⚠ Overwrite file* (amber) when the target already exists; previously the block showed the blue *✓ Create file* state until the chat was reloaded
- **Action block colour** — *Apply patch* block changed from purple to lime green (`#80c040`) on dark green background for better readability
- **Settings: Agentic tab layout** — *Enable agentic mode* and *Batch file confirmations* now share one row; the four Allow checkboxes are arranged in a 2 × 2 grid; a note explains disabled-action fallback behaviour; the prompt template textarea is collapsible (▶ / ▼ toggle) so the tab fits without scrolling

### 0.7.0
- **Agentic mode** — the LLM can take direct actions using special code fences; each action appears as a styled action block in the chat and requires a one-click confirmation before executing:
  - `` ```file:path/to/file.py `` — create or overwrite a file (path relative to project root or absolute); new file is automatically opened in the Spyder editor
  - `` ```run:python `` — send Python code to the active IPython console
  - `` ```install:pip `` — install one or more packages via the console
  - `` ```patch:path/to/file.py `` — apply a unified diff patch to an existing file
- **Agentic settings tab** (Settings → 🤖 Agentic): master enable switch, batch-confirm toggle, per-action allow flags (create file, run console, install, patch — install is off by default), default base path field with Browse button, and a customisable prompt template textarea pre-filled with the built-in default; **Reset to default** restores the built-in prompt
- **Overwrite detection** — `file:` action blocks show a blue "✓ Create file" button for new paths and an amber "⚠ Overwrite file" button when the target already exists
- **Action block colours** — create file = blue, overwrite = amber, run in console = green, install = teal, apply patch = purple; disabled action types fall back to plain code block rendering
- **Done badge** — after successful execution the action button is replaced by a **✓ Done** badge; hovering the badge reveals **↺ Re-run**; clicking re-runs the action
- **Execution persistence** — executed actions are stored in the chat JSON; on chat reload Done badges are shown immediately for previously executed blocks
- **Regenerate fix** — the 🔄 Regenerate button now correctly injects the agentic system prompt, so regenerated responses include agentic action fences as expected
- **Streaming flash fix** — eliminated the brief floating widget that appeared when an action block started rendering during streaming (parentless Qt widget visibility race)

### 0.6.0
- **Project-wide context** — enable the **📁 Proj. Context** toggle in the chat bar to attach your entire Spyder project to the conversation:
  - Folder-selection dialog with live token estimate; choose which top-level folders to include
  - First message sends all selected files in full; subsequent messages send only changed files as a delta
  - Open files with unsaved edits use the live editor buffer — the LLM always sees current state
  - New unsaved files (not yet saved to disk) are auto-included from the editor buffer
  - File watcher monitors the project directory; badge shows changed-file count before each send
  - Re-opening a saved chat restores project context; files re-expanded if hashes match, stale badge otherwise
  - Whole-file attachments blocked while project context is ON; editor selections and console attachments remain available
  - New **📁 Context** tab in Settings: max file size, max file count, extra exclusion glob patterns

### 0.5.1
- **Chat history search** — live search field in the history popup filters chats by title preview and full message content simultaneously as you type
- **Table `<br>` tag fix** — line breaks inside table cells now render correctly instead of appearing as literal `<br>` text
- **Table scroll fix** — mouse wheel over a rendered table now scrolls the chat window instead of scrolling the table widget independently

### 0.5.0
- **IPython console context menu** — right-click anywhere in the IPython console to access the **AI Chat** submenu: *Add console content to context* attaches the full console output; *Add selection to context* attaches the selected text; both support ANSI-escape stripping
- **Console attachment colour distinction** — console context tags in the input bar are rendered with a teal-green background (`#1e3a2a` / `#3a7a5a`) to visually distinguish them from blue editor/file tags
- **Think block show/hide scroll fix** — clicking the show/hide toggle on a thinking block no longer causes the chat window to jump to the bottom; scroll position is preserved
- **Live code block rendering** — code block widget appears as soon as the opening ` ``` ` line arrives during streaming and grows line by line; the widget is finalised (scrollbar, exact height) when the closing ` ``` ` is received
- **Code block height fixes** — height calculated from `fontMetrics().lineSpacing()` (instead of `pointSize()+8`); horizontal scrollbar height reserved; single-line blocks no longer clipped

### 0.4.1
- **Default system prompt for new chat** — Settings → System Prompts tab now has a "Default for new chat:" dropdown; the selected prompt is automatically applied to the system prompt field whenever a new chat is started
- **Think block streaming fix** — `<think>` blocks are now rendered as a collapsible Thinking widget immediately after `</think>` arrives during streaming, instead of remaining as raw text until the full response finishes
- **Nested list streaming fix** — nested list items now render with correct line breaks during progressive streaming
- **Code-only message fix** — messages consisting of a single code block no longer show an empty code widget; the block stays as raw text during streaming and renders correctly when the closing ` ``` ` arrives
- **`build_code_block` crash fix** — fixed `UnboundLocalError` that caused saved chats containing code blocks to fail loading after restart

### 0.4.0
- **Processing spinner** — a braille spinner (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`) is shown in the chat panel while waiting for the first LLM token; it disappears and the streaming response appears as soon as the first character arrives
- **Incremental markdown rendering** — the response is formatted in real time as it streams: completed blocks (headings, paragraphs, code fences, tables, blockquotes, think boxes) are promoted to rendered Qt widgets immediately; only the trailing incomplete block remains as live plain text
- **HTTP error display** — API errors (e.g. HTTP 403/500) now appear in a visually distinct dark-red box with an "⚠ Response error" header instead of unstyled text; no spurious empty "Assistant:" block is created on error
- **Delete on error blocks** — the delete button on an error response block now works correctly (previously a message-index mismatch caused it to silently fail)
- **Regenerate on error** — the Regenerate button now appears on error response blocks, allowing an immediate retry without clearing the conversation

### 0.3.2
- **Plugin entry-point renamed** from `ai_chat` to `ai_chat_plugin` (`spyder.plugins` entry point in `pyproject.toml`); FIM provider entry-point renamed from `ai_fim` to `ai_fim_provider` (`spyder.completions` entry point)
- **`NAME` and `CONF_SECTION`** in `AIChatPlugin` updated to `"ai_chat_plugin"` to stay consistent with the entry-point key
- **`COMPLETION_PROVIDER_NAME` and `CONF_SECTION`** in `AiFimProvider` updated to `"ai_fim_provider"` and `"ai_chat_plugin"` respectively

### 0.3.1
- **Settings → ⚡ Auto-complete tab** completely redesigned as a step-by-step wizard: enable checkbox → set provider/URL/key → **Load Models** → pick model + backend; previous tab was a flat form with no guidance
- **Load Models button** with braille spinner animation fetches the model list and automatically probes which FIM backends the endpoint supports; backend probe validates the response body (not just HTTP status 200) to avoid false positives from providers that return `{"error":…}` on unsupported endpoints
- **Model list and backend list persistence**: full dropdown contents saved to config on OK; restored on next open without needing to re-run Load Models
- **Test Connection button** added to the Connection tab — sends a `GET /models` probe and reports the number of available models; uses an OpenAI-SDK-style `User-Agent` header to avoid Cloudflare 403 (error 1010) blocks
- **Settings window** width increased by ~10%; tab bar stretches edge-to-edge with uniform padding
- **"🖊 Dialogs" tab** (renamed from "🖊 Editor") with descriptive info label at the top
- **System Prompts tab**: Edit button removed; selecting a prompt from the dropdown immediately enables editing; **💾 Save prompt** activates only when title or content has been modified
- **Commands tab**: Edit button removed; selecting a command immediately enables editing; **Save command** activates only when name or prompt has been modified
- **FIM cursor-offset fix**: cursor position now derived from `(blockNumber, columnNumber)` and converted with a line-ending-aware helper, eliminating stale completions when files use `\r\n` endings
- **Editor context menu** (Add file / Add selection) fixed: items re-injected on every `aboutToShow` event to survive Spyder's menu rebuild cycle
- **FIM default values**: temperature default changed to 0.5, context before/after cursor default changed to 100 characters

### 0.3.0
- **AI auto-complete (FIM)** — fill-in-middle ghost-text completions in the Spyder code editor (`fim/provider.py`); registered as a `spyder.completions` entry point
- **Ghost-text rendering**: grey inline suggestion after the cursor; **Tab** to accept, **Escape** to dismiss
- **Multi-backend support**: Ollama `/api/generate`, OpenAI-compat `/v1/completions`, Codestral `/v1/fim/completions`, chat-completions fallback
- **Trigger modes**: auto (debounce), after-newline, manual (**Alt+\\**)
- **Settings → FIM tab**: provider, URL, API key, model, backend type, max tokens, temperature, context window, trigger mode, debounce delay
- **Escape key fix**: intercepts `ShortcutOverride` event to prevent Spyder's global Escape shortcut from stealing the dismiss keystroke before the FIM provider can handle it
- Fixed: editor context-menu items "Add whole file to context" and "Add selection to context" now reliably appear and call the correct attachment handler

### 0.2.1
- **Slash-command aliases** (`commands.py`): define short aliases (e.g. `/tests`, `/explain`) that expand to full prompt text before being sent to the LLM; type `/` in the input to open a keyboard-navigable picker dropdown
- **5 built-in commands**: `/tests`, `/simplify`, `/fix`, `/explain`, `/doc` — auto-seeded on first run to `~/.spyder_ai_chat/commands.json`
- **Settings → / Commands tab**: create, edit, delete, and restore built-in commands; restoring built-ins does not affect user-defined commands
- **Command highlighting**: active command tokens shown with a green highlight in the input field and in sent chat bubbles
- **Chat history**: command spans stored in JSON (`command_spans`); original expanded prompt preserved in `content_llm` so history replay is correct even if a command is later edited or deleted
- **Chat history preview**: command-only messages now show `/command — filename.py` (attachment), `/command — user text`, or `/command — at yyyy-mm-dd hh:mm` (timestamp fallback) instead of the bare command name
- **LM Studio API key**: now optional (previously hidden) — shown in Connection tab for setups with authentication enabled
- **Connection tab UI**: added "Only one provider can be active at a time." info label, horizontal separator, and "Configure active provider:" label above the provider form
- **Settings → Connection tab**: rebuilt to use permanent form rows with show/hide instead of takeRow/addRow on provider switch (layout stability improvement)

### 0.2.0
- **12-provider support** with a provider registry in `settings_dialog.py`: OpenAI, Groq, Mistral AI, DeepSeek, Together AI, Fireworks AI, OpenRouter, Azure OpenAI, Ollama, LM Studio, vLLM, Custom — each with its own default URL, API key requirement, and supported inference parameters
- **Provider dropdown with grouping**: Local (Ollama, LM Studio, vLLM) / Cloud API / Custom sections with non-selectable separator headers
- **Per-chat inference hyperparameters popup**: temperature, max_tokens, top_p, top_k, min_p, presence_penalty, frequency_penalty, repetition_penalty, seed, num_ctx — only parameters supported by the selected provider are displayed; popup anchors above the params bar
- **Inference params bar** always visible above the system prompts row: idle state shows muted hint text; amber summary text when params are active; clicking opens the popup; resets on New Chat
- **Bottom panel redesign**: inference params bar → system prompts row (label + combo + ⚙ settings shortcut + Copy and edit) → system prompt field → input row (text field + stacked Send/Stop buttons)
- **⚙ shortcut** in system prompts row opens Settings directly on the System Prompts tab
- **Send/Stop stacked layout**: Send button takes ~66% of height, Stop ~34%, separated by 4 px gap
- Azure OpenAI extra fields (deployment name, API version) now correctly hide when switching away from the Azure provider
- Thinking block now uses a scrollable `QPlainTextEdit` (max-height 200 px) — eliminates all previous word-wrap and height-calculation issues
- Code blocks now use `QPlainTextEdit` with `NoWrap` mode and a horizontal scrollbar — long lines no longer clip
- Delete-all warmup reduced from 2 s hover to 1 s hover

### 0.1.9
- **Delete exchange buttons** on every user and assistant message: `🗑 This` removes the user+assistant pair, `⏫ All before` removes all preceding exchanges; both have a 3-second countdown with `↩ Cancel`
- **🔄 Regenerate button** on the last assistant message; moves automatically after deletion or regeneration
- Fixed: scroll position anchors to the bottom after markdown re-render completes
- Fixed: `clear_all` method restored; chat history loading no longer raises `AttributeError`

### 0.1.8
- New **Saved System Prompts** library (`system_prompts.py`)
- **Settings → 💬 System Prompts** tab: create, edit, delete saved prompts
- **Prompt selector bar** with dropdown and **📋 Copy to field** button
- Chat history stores `prompt_id`; restored on load

### 0.1.7
- Fully recursive list parser; mixed bullet/numbered types at any depth; blank-line-separated items
- Bullet symbols cycle by depth: `•` `◦` `▪` `▸`
- Numbered lists preserve source numbers
- Fixed: auto-scroll to bottom on send and during streaming
- Fixed: short responses no longer float in the middle of the chat area

### 0.1.6
- Menu path corrected: **Window → Panes → AI Chat**

### 0.1.5
- PyPI `README_PYPI.md` added; `[project.urls]` Homepage field in `pyproject.toml`

### 0.1.4
- Tabbed settings dialog: Connection, Editor, History tabs
- Configurable font sizes for all rendered markdown elements
- History saving options with correct enable/disable logic
- Horizontal scrollbar in chat area for wide code blocks
- File/text context attachments restructured; locked badges in user message bubbles

### 0.1.3
- `User-Agent` header added to fix 403 errors with Groq and some providers
- Improved HTTP error reporting

### 0.1.2
- Full markdown rendering (`markdown_renderer.py`): headings, bold/italic, lists, tables, blockquotes, links, strikethrough
- `<think>` block support with collapsible thinking box
- Chat history: save, load, delete, browse
- Auto-save after every completed exchange
- Editor context menu: Add whole file / Add selection to context

### 0.1.0
- Initial release: streaming chat, model selector, system prompt, stop button, code block rendering with Copy to editor

---

## License

MIT — see `LICENSE` file.
