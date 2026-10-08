"""Shellmate 命令行入口，负责解析参数并调用相应模块。"""

from __future__ import annotations

import argparse
import os
import sys

from shellmate.agent import AgentError, LangGraphAgent
from shellmate.config import (
    AGENT_PROMPT_PATH,
    CONFIG_PATH,
    DATA_DIR,
    ZSH_PLUGIN_PATH,
    ensure_data_dir,
    ensure_zsh_plugin,
    load_config,
)
from shellmate.context import ShellContext, read_context, read_zsh_history

# 管道模式输入的最大保留字符数；报错信息通常在输出末尾，故保留尾部。
_MAX_OUTPUT_CHARS = 20000


def _history_text(config, args) -> str:
    """历史来源优先级：zsh 插件经 --history 传入 > 环境变量 > 历史文件兜底。"""
    return (
        getattr(args, "history", "")
        or os.environ.get("SHELLMATE_HISTORY_TEXT", "")
        or read_zsh_history(config.shell.history_lines)
    )


def _thread_id(config, args) -> str:
    """会话 ID 来源优先级：--thread-id > zsh 会话环境变量 > 配置兜底。"""
    return (
        getattr(args, "thread_id", None)
        or os.environ.get("SHELLMATE_SESSION_ID")
        or config.thread_id
    )


def _ask(config, question: str, context: ShellContext, args) -> None:
    """运行 agent 并打印回答，统一异常处理。"""
    try:
        print(LangGraphAgent(config).ask(question, context, _thread_id(config, args)))
    except (AgentError, ValueError, OSError) as exc:
        print(f"shellmate: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> None:
    """处理初始化、提问、解释上一条命令与配置查看等子命令。"""
    parser = argparse.ArgumentParser(prog="shellmate", description="Ask an AI assistant about your shell session")
    sub = parser.add_subparsers(dest="command")
    ask_parser = sub.add_parser("ask", help="Ask a question using recent shell context")
    ask_parser.add_argument("question", nargs="*", help="Question; multiple words are joined with spaces")
    ask_parser.add_argument("--history", default="", help="Recent shell history supplied by the zsh plugin")
    ask_parser.add_argument("--thread-id", help="LangGraph conversation ID; normally supplied by zsh")
    explain_parser = sub.add_parser(
        "explain",
        help="Explain command output read from stdin (e.g. cmd 2>&1 | shellmate explain)",
    )
    explain_parser.add_argument("question", nargs="*", help="Optional question; defaults to summarizing the output")
    explain_parser.add_argument("--history", default="", help="Recent shell history supplied by the zsh plugin")
    explain_parser.add_argument("--thread-id", help="LangGraph conversation ID; normally supplied by zsh")
    last_parser = sub.add_parser(
        "explain-last",
        help="Explain the last command and its exit code (triggered by Ctrl-G on empty prompt)",
    )
    last_parser.add_argument("--history", default="", help="Recent shell history supplied by the zsh plugin")
    last_parser.add_argument("--thread-id", help="LangGraph conversation ID; normally supplied by zsh")
    sub.add_parser("init", help="Create the local configuration and Agent prompt files")
    sub.add_parser("config-path", help="Print the configuration file path")
    sub.add_parser("history-lines", help="Print the configured number of history lines")
    args = parser.parse_args()
    try:
        config = load_config()
    except (ValueError, OSError) as exc:
        print(f"shellmate: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    if args.command == "init":
        ensure_data_dir()
        zshrc_updated = ensure_zsh_plugin()
        print(f"已创建或确认配置文件：{CONFIG_PATH}")
        print(f"已创建或确认 Agent 提示词：{AGENT_PROMPT_PATH}")
        print(f"已创建或确认数据目录：{DATA_DIR}")
        print(f"已创建或确认 zsh 插件：{ZSH_PLUGIN_PATH}")
        if zshrc_updated:
            print("已在 ~/.zshrc 添加插件加载行，请执行 `source ~/.zshrc` 使其生效。")
        else:
            print("~/.zshrc 已包含插件加载行，无需修改。")
        return
    if args.command == "config-path":
        print(CONFIG_PATH)
        return
    if args.command == "history-lines":
        print(config.shell.history_lines)
        return

    if args.command == "explain-last":
        last_command = os.environ.get("SHELLMATE_LAST_COMMAND", "").strip()
        if not last_command:
            print("shellmate: 没有可解释的上一条命令。", file=sys.stderr)
            raise SystemExit(1)
        raw_exit = os.environ.get("SHELLMATE_LAST_EXIT", "").strip()
        try:
            exit_code = int(raw_exit)
        except ValueError:
            exit_code = None
        history = _history_text(config, args)
        context = ShellContext(history=history, last_command=last_command, last_exit_code=exit_code)
        if exit_code == 0:
            question = "解释一下刚才这条命令：它做了什么、输出或副作用是什么、有什么值得注意的地方。"
        else:
            question = "刚才这条命令失败了。结合退出码解释它为什么会失败，并给出如何排查和修复的具体建议。"
        _ask(config, question, context, args)
        return

    if args.command == "explain":
        if sys.stdin.isatty():
            print(
                "shellmate: explain 需要管道输入，例如：command 2>&1 | shellmate explain",
                file=sys.stderr,
            )
            raise SystemExit(1)
        output = sys.stdin.read()
        if not output.strip():
            print("shellmate: 标准输入为空。", file=sys.stderr)
            raise SystemExit(1)
        output = output[-_MAX_OUTPUT_CHARS:]
        question = " ".join(args.question).strip() or "解释这段命令输出：发生了什么、是否报错、以及该如何处理。"
        history = _history_text(config, args)
        context = ShellContext(history=history, output=output)
        _ask(config, question, context, args)
        return

    if args.command != "ask":
        parser.print_help()
        return

    if args.question:
        question = " ".join(args.question).strip()
    else:
        try:
            question = input("Ask Shellmate: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nshellmate: 未输入问题。", file=sys.stderr)
            raise SystemExit(1)
    if not question:
        print("shellmate: 未输入问题。", file=sys.stderr)
        raise SystemExit(1)
    context = read_context(_history_text(config, args))
    _ask(config, question, context, args)


if __name__ == "__main__":
    main()
