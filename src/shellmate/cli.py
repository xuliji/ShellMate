"""Shellmate 命令行入口，负责解析参数并调用相应模块。"""

from __future__ import annotations

import argparse
import os
import sys

from shellmate.agent import AgentError, LangGraphAgent
from shellmate.config import AGENT_PROMPT_PATH, CONFIG_PATH, DATA_DIR, ensure_data_dir, load_config
from shellmate.context import read_context, read_zsh_history


def main() -> None:
    """处理初始化、提问和配置查看等子命令。"""
    parser = argparse.ArgumentParser(prog="shellmate", description="Ask an AI assistant about your shell session")
    sub = parser.add_subparsers(dest="command")
    ask_parser = sub.add_parser("ask", help="Ask a question using recent shell context")
    ask_parser.add_argument("question", nargs="*", help="Question; multiple words are joined with spaces")
    ask_parser.add_argument("--history", default="", help="Recent shell history supplied by the zsh plugin")
    ask_parser.add_argument("--thread-id", help="LangGraph conversation ID; normally supplied by zsh")
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
        print(f"已创建或确认配置文件：{CONFIG_PATH}")
        print(f"已创建或确认 Agent 提示词：{AGENT_PROMPT_PATH}")
        print(f"已创建或确认数据目录：{DATA_DIR}")
        return
    if args.command == "config-path":
        print(CONFIG_PATH)
        return
    if args.command == "history-lines":
        print(config.shell.history_lines)
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
    try:
        # 历史来源优先级：zsh 插件经 --history 传入 > 环境变量 > 历史文件兜底。
        history = (
            args.history
            or os.environ.get("SHELLMATE_HISTORY_TEXT", "")
            or read_zsh_history(config.shell.history_lines)
        )
        context = read_context(history)
        thread_id = args.thread_id or os.environ.get("SHELLMATE_SESSION_ID") or config.thread_id
        print(LangGraphAgent(config).ask(question, context, thread_id))
    except (AgentError, ValueError, OSError) as exc:
        print(f"shellmate: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
