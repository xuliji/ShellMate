# Shellmate

Shellmate is an AI troubleshooting assistant for the zsh command line. The zsh integration gathers recent command history; a LangGraph agent uses a single OpenAI-compatible protocol for OpenAI, DeepSeek, Qwen, and other compatible endpoints. A built-in DuckDuckGo HTML search tool needs no search API key. Pydantic validates configuration, TypedDict defines graph state, and a local SQLite file stores checkpoints partitioned by zsh session ID.

## Project layout

```text
Shellmate/
├── pyproject.toml                   # Package metadata and dependencies
├── MANIFEST.in                      # Includes the zsh plugin in the source distribution
├── src/
│   └── shellmate/
│       ├── agent.py                 # LangGraph graph and SQLite checkpointing
│       ├── cli.py                   # shellmate CLI and init command
│       ├── config.py                # Pydantic configuration models and initialization
│       ├── context.py               # Recent zsh history formatting
│       ├── privacy.py               # Secret-redaction middleware
│       └── tools/
│           └── web_search.py        # DuckDuckGo HTML search tool
└── zsh/
    └── shellmate.zsh                # Ctrl-G widget and history collection

~/.config/shellmate/
├── config.json                      # User model and Shellmate settings
├── Agent.md                         # Editable system prompt
└── data/
    └── checkpoints.sqlite           # LangGraph state, created after the first question
```

## Install for development

```sh
python -m pip install -e .
```

Then initialize the local configuration:

```sh
shellmate init
```

On first run, Shellmate creates `~/.config/shellmate/config.json` and `~/.config/shellmate/Agent.md`. Edit the JSON file to add your model API key; edit `Agent.md` to customize the agent instructions:

```json
{
  "llm": {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "api_key": ""
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

All model services use one OpenAI-compatible protocol. Configure `llm.base_url`, `llm.model`, and `llm.api_key` for OpenAI, DeepSeek, Qwen, or another compatible endpoint. `OPENAI_API_KEY` and `SHELLMATE_API_KEY` can supply the API key; environment variables override JSON settings. No database service is required: `~/.config/shellmate/data/checkpoints.sqlite` stores LangGraph checkpoints. The zsh widget generates a stable session ID for each shell session; direct CLI use can optionally pass `--thread-id`, otherwise an internal default is used. Pydantic validates configuration before the agent starts.

Redaction is enabled by default. It covers common API keys, password/token assignments, Bearer tokens, AWS access keys, and PEM private-key blocks. Optional Python regular expressions can be added in `privacy.custom_patterns`; matches are replaced with `[REDACTED]`. Redaction is best-effort and cannot identify every secret format.

The search tool submits a query to DuckDuckGo's lightweight HTML search page and parses result titles, links, and snippets with Python's standard library. This avoids a paid search API key, but the public page may rate-limit requests or change its markup.

Add this line to `~/.zshrc`:

```zsh
source /path/to/Shellmate/zsh/shellmate.zsh
```

Restart zsh, then press **Ctrl-G** to ask about the session. You can also run `shellmate ask "Why did my last command fail?"`.

`shellmate init` explicitly creates the configuration file, Agent prompt, and `~/.config/shellmate/data/` directory without overwriting existing files.

## Terminal output

Shellmate prints its answer directly to the current zsh terminal and does not write a response file. It reads recent zsh command history, but does not capture terminal scrollback or command stdout/stderr; paste error output into your question when needed.

## Privacy

Context is sent to the configured model endpoint only when the user invokes Shellmate. Recent command history can contain secrets; review the configured endpoint. Shellmate does not execute model-suggested commands.
