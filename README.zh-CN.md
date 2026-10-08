# Shellmate

Shellmate 是一个面向 zsh 的命令行 AI 助手。按下快捷键后，它会收集近期命令历史，经脱敏中间件处理后，把问题与上下文发送给 OpenAI 兼容模型，并可按需调用联网搜索工具。Agent 使用 LangGraph 构图，Pydantic 校验配置，TypedDict 定义图状态；checkpoint 保存在本地 SQLite 文件中。

## 功能

- 通过 zsh widget 使用快捷键唤起 Shellmate（默认 `Ctrl-G`）。
- 将近期 zsh 命令历史作为问题上下文。
- 使用 OpenAI 兼容协议连接 OpenAI、DeepSeek、Qwen 等模型服务；通过地址、模型名和 API Key 配置目标服务。
- 使用 LangGraph 构建模型与工具节点，以 TypedDict 描述图状态。
- 使用 Pydantic 校验配置文件；使用本地 SQLite 保存 LangGraph checkpoint。
- 默认在模型请求和搜索请求前脱敏常见密钥、密码、Bearer Token、AWS Access Key 和 PEM 私钥。
- 内置 DuckDuckGo HTML 网页搜索，不需要 Brave Search API 或搜索 API Key。
- Shellmate 只提供解释和建议，不会自动执行模型建议的命令。

## 项目结构

```text
Shellmate/
├── pyproject.toml                   # 打包元数据和依赖
├── MANIFEST.in                      # 将 zsh 插件纳入 source distribution
├── src/
│   └── shellmate/
│       ├── agent.py                 # LangGraph 状态图和 SQLite checkpoint
│       ├── cli.py                   # shellmate 命令行入口和 init 命令
│       ├── config.py                # Pydantic 配置模型和初始化逻辑
│       ├── context.py               # 近期 zsh 命令历史格式化
│       ├── privacy.py               # 脱敏中间件
│       └── tools/
│           └── web_search.py        # DuckDuckGo HTML 搜索工具
└── zsh/
    └── shellmate.zsh                # Ctrl-G 快捷键和历史采集

~/.config/shellmate/
├── config.json                      # 用户模型和 Shellmate 配置
├── Agent.md                         # 可编辑的 Agent 系统提示词
└── data/
    └── checkpoints.sqlite           # LangGraph 状态，首次提问后创建
```

## 安装

Shellmate 当前以源码开发安装为主。需要 Python 3.11 或更新版本：

```sh
cd /path/to/Shellmate
python -m pip install -e .
```

安装后执行一次初始化：

```sh
shellmate init
```

## 配置

首次运行 Shellmate 时会自动创建 `~/.config/shellmate/config.json` 和 `~/.config/shellmate/Agent.md`。前者写入下面的默认配置模板，用于填写模型 API Key；后者用于编辑 Agent 系统提示词：

```json
{
  "llm": {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": "",
    "timeout": 60
  },
  "shell": {
    "history_lines": 20
  },
  "search": {
    "endpoint": "https://html.duckduckgo.com/html/"
  },
  "privacy": {
    "redact_secrets": true,
    "custom_patterns": []
  }
}
```

无需部署数据库服务。LangGraph checkpoint 保存在 `~/.config/shellmate/data/checkpoints.sqlite`，并使用当前 zsh 会话 ID 隔离。zsh 插件会为每个 shell 会话生成稳定的会话 ID；直接运行 CLI 时可选传 `--thread-id`，未传时使用内部默认值。

配置由 Pydantic 模型校验：未知字段、错误类型、无效的历史条数或超出范围的超时会在启动时报告配置错误。

所有模型统一使用 OpenAI 兼容协议。切换到 DeepSeek、Qwen 或其他兼容服务时，设置服务提供的 `llm.base_url`、`llm.model` 和 API Key 即可，不需要 Provider 注册表或厂商专用代码。

`privacy.redact_secrets` 默认为 `true`。可以在 `custom_patterns` 中添加 Python 正则表达式；匹配内容会替换为 `[REDACTED]`。例如：

```json
"privacy": {
  "redact_secrets": true,
  "custom_patterns": ["公司内部项目代号-[A-Z0-9]+"]
}
```

脱敏发生在请求发往模型之前，也会应用于发往搜索服务的查询词和模型可见的工具结果。脱敏是基于规则的尽力处理，不能保证识别所有秘密格式；请勿把它视为阻止敏感信息外发的唯一措施。关闭 `redact_secrets` 会原样发送上下文。

模型 API 密钥建议通过环境变量设置，也可以写入 `llm.api_key`：

```sh
export OPENAI_API_KEY="你的模型 API 密钥"
```

`SHELLMATE_BASE_URL`、`SHELLMATE_MODEL` 和 `SHELLMATE_API_KEY` 可以覆盖对应 JSON 设置；`OPENAI_API_KEY` 也可作为 API Key 环境变量。

Shellmate 自带网页搜索实现，默认请求 DuckDuckGo 的轻量 HTML 搜索页面，不需要申请或配置搜索 API Key。需要时可通过 `search.endpoint` 或 `SHELLMATE_SEARCH_ENDPOINT` 覆盖搜索页面地址。公共搜索页面可能限流或调整页面结构；发生变化时需要更新本项目的 HTML 解析器。

## 配置 zsh 快捷键

在 `~/.zshrc` 中加入（将路径替换为本地项目路径）：

```zsh
source /path/to/Shellmate/zsh/shellmate.zsh
```

重新打开终端或执行 `source ~/.zshrc`。在 zsh 中按 `Ctrl-G`，输入问题并回车，即可让 Shellmate 结合近期命令历史回答。同一 zsh 进程复用同一个 LangGraph thread，不同 shell 进程使用不同 thread ID。

## 命令行用法

直接提问：

```sh
shellmate ask "刚才的命令为什么失败？"
```

不传问题时会进入交互式提问：

```sh
shellmate ask
```

也可以手动传入历史上下文：

```sh
shellmate ask --history $'ls -la\ngit status' "工作区里有哪些未提交的改动？"
```

查看配置路径和当前历史行数：

```sh
shellmate config-path
shellmate history-lines
```

`shellmate init` 可显式创建配置、Agent 提示词和 `~/.config/shellmate/data/` 数据目录；已有文件不会被覆盖。

## 终端输出

Shellmate 的回答由 CLI 直接打印到当前 zsh 终端，不另写回答文件。Shellmate 只读取 zsh 命令历史，不会捕获终端滚屏中的 stdout/stderr；提问时可把报错内容粘贴进问题。

## 隐私说明

只有在你主动调用 Shellmate 时，近期命令历史和问题才会随请求发送到配置的模型服务。命令参数可能含有密钥、路径和其他敏感信息；请确认模型服务地址可信。联网搜索会把脱敏后的搜索词发送给 DuckDuckGo。

## 当前限制

- zsh 集成只采集近期命令历史，不读取终端滚屏输出。
- 搜索工具由 Shellmate 使用 Python 标准库实现，通过 DuckDuckGo HTML 页面获取结果，不依赖 Brave API Key。公共搜索页面可能限流或变更，稳定性低于正式搜索 API。
- LangGraph 通过 OpenAI 兼容 Chat Completions 接口连接模型；所选模型需要支持工具调用。SQLite 适合本地单用户使用，不适合多个进程高并发写入。
