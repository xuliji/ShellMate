# Shellmate

[🇨🇳 简体中文](README.md) | 🇬🇧 English

[![PyPI](https://img.shields.io/pypi/v/shellmate-ai?color=blue)](https://pypi.org/project/shellmate-ai/)
[![Python](https://img.shields.io/pypi/pyversions/shellmate-ai.svg)](https://pypi.org/project/shellmate-ai/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Shellmate is an AI assistant for your zsh command line. Type a question and press **Ctrl-G** — it answers using your recent command history and any OpenAI-compatible model (OpenAI, DeepSeek, Qwen, …).

## Features

- **Ctrl-G** widget — type a question and press Ctrl-G; **press Ctrl-G on an empty prompt to explain the last command**
- Streaming responses, printed token by token
- Inline Markdown rendering in the terminal (syntax-highlighted code, tables, lists)
- Automatically captures the last command and its exit code to diagnose failures
- Recent command history as context
- OpenAI-compatible protocol — OpenAI / DeepSeek / Qwen / other endpoints
- Built-in DuckDuckGo web search, no API key required
- Secret redaction before model and search requests (including high-entropy key detection)
- Local SQLite checkpoints, no database service

## Install

Requires Python 3.11+.

```sh
pip install shellmate-ai   # or: pip install -e . from a checkout
shellmate-ai init          # creates config + zsh plugin + .zshrc entry
source ~/.zshrc            # or open a new terminal
```

> **Note**: the installed command is `shellmate-ai` (matching the PyPI package name).

## Usage

In zsh, type a question and press **Ctrl-G**. **Press Ctrl-G on an empty prompt** to explain the last command (with its exit code) and why it failed.

```sh
shellmate-ai ask "Why did my last command fail?"          # ask directly
shellmate-ai ask                                          # interactive prompt
shellmate-ai ask --history $'ls -la\ngit status' "..."    # pass history manually

# Feed command output to Shellmate for explanation (pipe mode)
git push origin main 2>&1 | shellmate-ai explain
tail -200 app.log | shellmate-ai explain "why does it keep timing out?"

shellmate-ai explain-last                                 # explain the last command (Ctrl-G on empty prompt)
shellmate-ai config-path                                  # print config path
shellmate-ai history-lines                                # print history size
```

## Configuration

`shellmate-ai init` creates `~/.config/shellmate/config.json` and `Agent.md`. Set your API key there or via environment variables.

```json
{
  "llm": { "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "api_key": "" },
  "shell": { "history_lines": 20 },
  "search": { "endpoint": "https://html.duckduckgo.com/html/" },
  "privacy": { "redact_secrets": true, "redact_high_entropy": true, "custom_patterns": [] }
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
├── zsh_plugin.py      # bundled zsh plugin (loads shellmate.zsh data file)
├── shellmate.zsh      # zsh plugin (Ctrl-G / preexec / precmd)
└── tools/
    └── web_search.py  # DuckDuckGo HTML search
```

## License

[MIT](LICENSE)
