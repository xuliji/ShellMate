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
- 内置 DuckDuckGo 网页搜索，无需搜索 API Key
- 模型与搜索请求前自动脱敏（含高熵密钥检测）
- 本地 SQLite 保存 checkpoint，无需数据库服务

## 安装

需要 Python 3.11+。

```sh
pip install shellmate-ai   # 或从源码：pip install -e .
shellmate-ai init          # 创建配置 + zsh 插件 + .zshrc 加载行
source ~/.zshrc            # 或重开终端
```

> **注**：安装后命令行工具名为 `shellmate-ai`（与 PyPI 包名一致）。

## 使用

在 zsh 中输入问题，然后按 **Ctrl-G**。**空缓冲按 Ctrl-G**（命令行没有输入内容）会自动结合上一条命令及其退出码，解释它为什么失败。

命令失败时（非零退出码），提示符上方会出现提示：按 **Ctrl-X** 会把上一条命令用 `2>&1 | shellmate-ai explain` 重跑，让 agent 看到完整报错再解释（重跑可能有副作用，所以由你手动触发）。

```sh
shellmate-ai ask "刚才的命令为什么失败？"              # 直接提问
shellmate-ai ask                                      # 交互式提问
shellmate-ai ask --history $'ls -la\ngit status' "..." # 手动传历史

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
  "llm": { "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "api_key": "" },
  "shell": { "history_lines": 20 },
  "search": { "endpoint": "https://html.duckduckgo.com/html/" },
  "privacy": { "redact_secrets": true, "redact_high_entropy": true, "custom_patterns": [] }
}
```

环境变量会覆盖 JSON 配置：

| 变量 | 覆盖 |
| --- | --- |
| `OPENAI_API_KEY` / `SHELLMATE_API_KEY` | `llm.api_key` |
| `SHELLMATE_BASE_URL` | `llm.base_url` |
| `SHELLMATE_MODEL` | `llm.model` |
| `SHELLMATE_SEARCH_ENDPOINT` | `search.endpoint` |

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

- **system_prompt** — 加载可编辑的 `Agent.md` 作为系统提示词（每个会话加载一次）
- **assistant** — 携带消息历史调用 OpenAI 兼容模型
- **tools** — 模型请求联网时执行 DuckDuckGo 搜索

## 项目结构

```text
src/shellmate/
├── agent.py           # LangGraph agent + SQLite checkpoint
├── cli.py             # 命令行入口
├── config.py          # Pydantic 配置
├── context.py         # 历史格式化
├── privacy.py         # 脱敏中间件
├── zsh_plugin.py      # 内置 zsh 插件（从 shellmate.zsh 数据文件读取）
├── shellmate.zsh      # zsh 插件（Ctrl-G / preexec / precmd）
├── prompts/
│   └── Agent.md       # 默认系统提示词模板（init 时写入配置目录）
└── tools/
    └── web_search.py  # DuckDuckGo HTML 搜索
```

## License

[MIT](LICENSE)
