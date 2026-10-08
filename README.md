# Shellmate

🇨🇳 简体中文 | [🇬🇧 English](README.en.md)

[![PyPI](https://img.shields.io/pypi/v/shellmate-ai?color=blue)](https://pypi.org/project/shellmate-ai/)
[![Python](https://img.shields.io/pypi/pyversions/shellmate-ai.svg)](https://pypi.org/project/shellmate-ai/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Shellmate 是一个面向 zsh 的命令行 AI 助手。在命令行输入问题后按 **Ctrl-G**，它会结合近期命令历史，用任意 OpenAI 兼容模型（OpenAI、DeepSeek、Qwen 等）给出回答。

## 功能

- **Ctrl-G** 快捷键 — 输入问题按 Ctrl-G 提问；**空缓冲按 Ctrl-G 自动解释上一条命令**
- 终端内渲染 Markdown（代码高亮、表格、列表）
- 自动捕获上一条命令及其退出码，失败时结合退出码定位原因
- 命令失败后在提示符上方给出提示，按 **Ctrl-X** 用管道重跑、让 agent 看完整报错
- 近期命令历史作为上下文
- OpenAI 兼容协议，支持 OpenAI / DeepSeek / Qwen 等
- 系统提示词可编辑（`~/.config/shellmate/Agent.md`），默认模板随包下发
- 内置 DuckDuckGo 网页搜索，无需搜索 API Key
- 模型与搜索请求前自动脱敏：密钥前缀、高熵 token、`KEY=value`、引号包裹的秘密、Webhook URL、URL 内嵌凭据、`curl -u` / `mysql -pXXX` 等命令行开关
- 本地 SQLite 保存会话记忆（checkpoint），无需数据库服务

## 安装

需要 Python 3.11+。

```sh
pip install shellmate-ai   # 或从源码：pip install -e .
shellmate-ai init          # 创建配置 + Agent 提示词 + zsh 插件 + .zshrc 加载行
source ~/.zshrc            # 或重开终端
```

> **注**：安装后命令行工具名为 `shellmate-ai`（与 PyPI 包名一致）。

## 使用

在 zsh 中输入问题，然后按 **Ctrl-G**。**空缓冲按 Ctrl-G**（命令行没有输入内容）会解释上一条命令 —— 但它只拿得到命令本身和退出码：**命令的输出没有被捕获**。原因是 zsh 没有"命令执行结束"的钩子，输出在提示符重绘时就已经消失了。想让 agent 看到真正的报错，用 **Ctrl-X** 或自己接管道。

| 触发方式 | agent 能看到什么 |
| --- | --- |
| Ctrl-G（命令行有输入） | 你的问题 + 近期命令历史 |
| Ctrl-G（空缓冲） | 上一条命令 + 退出码 + 近期历史，**不含该命令的输出** |
| Ctrl-X | 重新执行上一条命令，把 stdout+stderr 合并后的输出交给 agent |
| `cmd 2>&1 \| shellmate-ai explain` | 同上，但要跑哪条命令由你自己决定 |

命令失败时（非零退出码），提示符上方会出现提示：按 **Ctrl-X** 会把上一条命令用 `2>&1 | shellmate-ai explain` 重跑，把合并后的输出交给 agent 解释（重跑可能有副作用，所以由你手动触发）。

> **注**：Ctrl-X 任何时候都可用，不限于失败之后；输出过长时只保留末尾 2 万字符。`^X` 同时是 zsh 默认键位的前缀（如 `^X^U` 撤销、`^Xr` 历史搜索），所以 ZLE 会先等待 `KEYTIMEOUT`（默认 0.4 秒）再触发重跑——那些 `^X` 开头的组合键不受影响，觉得迟滞可以自行调小 `KEYTIMEOUT`。

```sh
shellmate-ai ask "刚才的命令为什么失败？"                    # 直接提问
shellmate-ai ask                                            # 交互式提问
shellmate-ai ask --history $'ls -la\ngit status' "解释一下"  # 手动传历史
shellmate-ai ask --thread-id my-task "换个新会话"            # 指定会话 ID

# 把命令输出喂给 Shellmate 解释（管道模式）
git push origin main 2>&1 | shellmate-ai explain
tail -200 app.log | shellmate-ai explain "为什么一直报 timeout？"

shellmate-ai explain-last                             # 解释上一条命令（Ctrl-G 空缓冲触发）
shellmate-ai config-path                              # 查看配置路径
shellmate-ai history-lines                            # 查看历史条数
```

## 配置

`shellmate-ai init` 会创建 `~/.config/shellmate/config.json` 和 `Agent.md`。在 config.json 中填入 API Key，或用环境变量设置。

`Agent.md` 是系统提示词，可以直接编辑：初始内容来自包内模板 `src/shellmate/prompts/Agent.md`（随 wheel/sdist 一起下发），只在文件不存在时写入，不会覆盖你的修改；改动对新会话生效。

```json
{
  "llm": { "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "api_key": "", "timeout": 60.0 },
  "shell": { "history_lines": 20 },
  "search": { "endpoint": "https://html.duckduckgo.com/html/" },
  "privacy": { "redact_secrets": true, "redact_high_entropy": true, "custom_patterns": [] }
}
```

字段约束：`llm.timeout` 大于 0 且不超过 600 秒，`shell.history_lines` 为 1–500，`search.endpoint` 必须是 HTTP(S) URL；`privacy.custom_patterns` 是额外的正则，命中后替换为 `[REDACTED]`；关闭 `privacy.redact_secrets` 会同时停用高熵检测。配置中出现未知字段（含已移除的 `provider`、`output_file`、`checkpoint`）会直接报错并指出字段名，不会被静默忽略。

环境变量会覆盖 JSON 配置：

| 变量 | 覆盖 |
| --- | --- |
| `OPENAI_API_KEY` / `SHELLMATE_API_KEY` | `llm.api_key` |
| `SHELLMATE_BASE_URL` | `llm.base_url` |
| `SHELLMATE_MODEL` | `llm.model` |
| `SHELLMATE_THREAD_ID` | `thread_id`（会话记忆 ID，默认 `shellmate-cli-default`） |
| `SHELLMATE_SEARCH_ENDPOINT` | `search.endpoint` |

CLI 另外会读取 `SHELLMATE_SESSION_ID`（未指定 `--thread-id` 时的会话 ID，由 zsh 插件按窗口设置），以及 `SHELLMATE_HISTORY_TEXT`、`SHELLMATE_LAST_COMMAND`、`SHELLMATE_LAST_EXIT` 作为兜底值 —— 新版插件改用命令行参数传这些内容，环境变量只为兼容已安装的旧插件保留。未设置 `HISTFILE` 时，历史文件按 `~/.zsh_history` 读取。

### 运行时文件

| 路径 | 说明 |
| --- | --- |
| `~/.config/shellmate/config.json` | 配置，权限 600 |
| `~/.config/shellmate/Agent.md` | 系统提示词，权限 600，可自由编辑 |
| `~/.config/shellmate/shellmate.zsh` | zsh 插件，由 `shellmate-ai init` 写入，权限 644 |
| `~/.config/shellmate/data/checkpoints.sqlite` | 会话记忆，SQLite，目录权限 700 |
| `~/.zshrc` | 由 `init` 幂等追加 `source ~/.config/shellmate/shellmate.zsh` |

## 架构

Agent 是一个 LangGraph 状态机：

```mermaid
flowchart TD
    Start([start]) --> SystemPrompt["system_prompt<br/>加载 Agent.md"]
    SystemPrompt --> Assistant["assistant<br/>调用模型"]
    Assistant -->|需要工具| Tools["tools<br/>网页搜索"]
    Assistant -->|结束| End([end])
    Tools --> Assistant
```

- **system_prompt** — 某个会话首次执行时读取可编辑的 `Agent.md`，作为系统提示词写入状态（每个会话一次）
- **assistant** — 把系统提示词置于最前，仅对会话消息脱敏后调用 OpenAI 兼容模型
- **tools** — 模型请求联网时执行 DuckDuckGo 搜索

## 项目结构

```text
src/shellmate/
├── agent.py           # LangGraph agent + SQLite checkpoint
├── cli.py             # 命令行入口
├── config.py          # Pydantic 配置 + 读取包内默认提示词
├── context.py         # 历史格式化
├── privacy.py         # 脱敏中间件
├── zsh_plugin.py      # 内置 zsh 插件（从 shellmate.zsh 数据文件读取）
├── shellmate.zsh      # zsh 插件（Ctrl-G / Ctrl-X / preexec / precmd）
├── prompts/
│   └── Agent.md       # 默认系统提示词模板（init 时写入配置目录）
└── tools/
    └── web_search.py  # DuckDuckGo HTML 搜索
```

## License

[MIT](LICENSE)
