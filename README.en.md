# Shellmate

[🇨🇳 简体中文](README.md) | 🇬🇧 English

Shellmate is an AI assistant for your zsh command line. Type a question and press **Ctrl-G** — it answers using your recent command history and any OpenAI-compatible model (OpenAI, DeepSeek, Qwen, …).

## Features

- **Ctrl-G** widget — type a question, press Ctrl-G to ask
- Recent command history as context
- OpenAI-compatible protocol — OpenAI / DeepSeek / Qwen / other endpoints
- Built-in DuckDuckGo web search, no API key required
- Secret redaction before model and search requests
- Local SQLite checkpoints, no database service

## Install

Requires Python 3.11+.

```sh
pip install shellmate   # or: pip install -e . from a checkout
shellmate init          # creates config + zsh plugin + .zshrc entry
source ~/.zshrc         # or open a new terminal
```

## Usage

In zsh, type a question and press **Ctrl-G**.

```sh
shellmate ask "Why did my last command fail?"          # ask directly
shellmate ask                                          # interactive prompt
shellmate ask --history $'ls -la\ngit status' "..."    # pass history manually
shellmate config-path                                  # print config path
shellmate history-lines                                # print history size
```

## Configuration

`shellmate init` creates `~/.config/shellmate/config.json` and `Agent.md`. Set your API key there or via environment variables.

```json
{
  "llm": { "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "api_key": "" },
  "shell": { "history_lines": 20 },
  "search": { "endpoint": "https://html.duckduckgo.com/html/" },
  "privacy": { "redact_secrets": true, "custom_patterns": [] }
}
```

Environment variables override JSON settings:

| Variable | Overrides |
| --- | --- |
| `OPENAI_API_KEY` / `SHELLMATE_API_KEY` | `llm.api_key` |
| `SHELLMATE_BASE_URL` | `llm.base_url` |
| `SHELLMATE_MODEL` | `llm.model` |
| `SHELLMATE_SEARCH_ENDPOINT` | `search.endpoint` |

## Architecture

The agent is a LangGraph state machine:

```mermaid
flowchart TD
    Start([start]) --> SystemPrompt["system_prompt<br/>load Agent.md"]
    SystemPrompt --> Assistant["assistant<br/>call model"]
    Assistant -->|tool call| Tools["tools<br/>web search"]
    Assistant -->|end| End([end])
    Tools --> Assistant
```

- **system_prompt** — loads the editable `Agent.md` as the system message (once per session)
- **assistant** — calls the OpenAI-compatible model with the message history
- **tools** — runs the DuckDuckGo web search when the model requests it

## Project layout

```text
src/shellmate/
├── agent.py           # LangGraph agent + SQLite checkpoints
├── cli.py             # CLI entry point
├── config.py          # Pydantic configuration
├── context.py         # history formatting
├── privacy.py         # secret redaction
├── zsh_plugin.py      # bundled zsh plugin
└── tools/
    └── web_search.py  # DuckDuckGo HTML search
zsh/shellmate.zsh      # zsh widget (Ctrl-G)
```
