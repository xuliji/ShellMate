"""Shellmate 命令行入口，负责解析参数并调用相应模块。"""

from __future__ import annotations

import argparse
import sys

from shellmate.agent import AgentError, LangGraphAgent
from shellmate.config import load_config
from shellmate.context import read_context


def main() -> None:
    """处理提问、记录输出和查看配置等子命令。"""
    parser = argparse.ArgumentParser(prog="shellmate", description="Ask an AI assistant about your shell session")
    sub = parser.add_subparsers(dest="command")
    ask_parser = sub.add_parser("ask", help="Ask a question using recent shell context")
    ask_parser.add_argument("question", nargs="?", help="Question; if omitted, prompt interactively")
    ask_parser.add_argument("--history", default="", help="Recent shell history supplied by the zsh plugin")
    ask_parser.add_argument("--thread-id", help="LangGraph conversation ID; normally supplied by zsh")
    sub.add_parser("config-path", help="Print the configuration file path")
    sub.add_parser("history-lines", help="Print the configured number of history lines")
    args = parser.parse_args()
    try:
        config = load_config()
    except (ValueError, OSError) as exc:
        print(f"shellmate: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if args.command == "config-path":
        from shellmate.config import CONFIG_PATH
        print(CONFIG_PATH)
        return
    if args.command == "history-lines":
        print(config.shell.history_lines)
        return
    if args.command != "ask":
        parser.print_help()
        return
    question = args.question or input("Ask Shellmate: ")
    try:
        # zsh 插件传入当前会话的近期命令历史。
        context = read_context(args.history)
        thread_id = args.thread_id or config.thread_id
        print(LangGraphAgent(config).ask(question, context, thread_id))
    except (AgentError, ValueError, OSError) as exc:
        print(f"shellmate: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
