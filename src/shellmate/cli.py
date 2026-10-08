"""Shellmate 命令行入口，负责解析参数并调用相应模块。"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
import threading

from rich.console import Console
from rich.markdown import Markdown

from shellmate import __version__
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


_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class _Spinner:
    """在 stderr 上显示单行动态加载态，退出时清除该行。

    用 ``\\r`` 回到行首再覆盖，不用多行光标移动，避免在 zsh/zle 等环境
    出现重复或残留。
    """

    def __init__(self, message: str) -> None:
        self._message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        for char in itertools.cycle(_SPINNER_CHARS):
            if self._stop.is_set():
                break
            sys.stderr.write(f"\r{char} {self._message}")
            sys.stderr.flush()
            self._stop.wait(0.08)

    def __enter__(self) -> "_Spinner":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=1)
        sys.stderr.write("\r\x1b[K")
        sys.stderr.flush()


def _ask(config, question: str, context: ShellContext, args) -> None:
    """运行 agent 并打印回答，统一异常处理。

    生成期间在 stderr 显示动态加载态；TTY 下用 rich 一次性渲染 Markdown，
    非 TTY（管道/重定向）则输出纯 Markdown 文本。
    """
    try:
        agent = LangGraphAgent(config)
        to_tty = sys.stdout.isatty()
        if sys.stderr.isatty():
            with _Spinner(f"正在请求 {config.llm.model} …"):
                result = agent.ask(question, context, _thread_id(config, args))
        else:
            result = agent.ask(question, context, _thread_id(config, args))
        if to_tty:
            Console().print(Markdown(result))
        else:
            print(result)
    except (AgentError, ValueError, OSError) as exc:
        print(f"shellmate-ai: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def main() -> None:
    """处理初始化、提问、解释上一条命令与配置查看等子命令。"""
    parser = argparse.ArgumentParser(prog="shellmate-ai", description="结合当前 shell 会话向 AI 提问")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    ask_parser = sub.add_parser("ask", help="结合近期命令历史提问")
    ask_parser.add_argument("question", nargs="*", help="要问的问题；多个词会用空格连接")
    ask_parser.add_argument("--history", default="", help="近期命令历史，由 zsh 插件传入")
    ask_parser.add_argument("--thread-id", help="LangGraph 会话 ID，通常由 zsh 传入")
    explain_parser = sub.add_parser(
        "explain",
        help="解释从标准输入读到的命令输出（如 cmd 2>&1 | shellmate-ai explain）",
    )
    explain_parser.add_argument("question", nargs="*", help="可选问题；默认总结这段输出")
    explain_parser.add_argument("--history", default="", help="近期命令历史，由 zsh 插件传入")
    explain_parser.add_argument("--thread-id", help="LangGraph 会话 ID，通常由 zsh 传入")
    last_parser = sub.add_parser(
        "explain-last",
        help="解释上一条命令及其退出码（空缓冲按 Ctrl-G 触发）",
    )
    last_parser.add_argument("--history", default="", help="近期命令历史，由 zsh 插件传入")
    last_parser.add_argument("--thread-id", help="LangGraph 会话 ID，通常由 zsh 传入")
    last_parser.add_argument("--last-command", default="", help="上一条命令，由 zsh 插件传入")
    last_parser.add_argument("--last-exit", default="", help="上一条命令的退出码，由 zsh 插件传入")
    sub.add_parser("init", help="创建本地配置、Agent 提示词、数据目录和 zsh 插件")
    sub.add_parser("config-path", help="打印配置文件路径")
    sub.add_parser("history-lines", help="打印配置的历史条数")
    args = parser.parse_args()
    try:
        config = load_config()
    except (ValueError, OSError) as exc:
        print(f"shellmate-ai: {exc}", file=sys.stderr)
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
        # 优先使用插件通过参数传入的值；环境变量仅作为旧版插件的兜底，
        # 因为导出的环境变量会被之后启动的所有子进程继承。
        last_command = (args.last_command or os.environ.get("SHELLMATE_LAST_COMMAND", "")).strip()
        if not last_command:
            print("shellmate-ai: 没有可解释的上一条命令。", file=sys.stderr)
            raise SystemExit(1)
        raw_exit = (args.last_exit or os.environ.get("SHELLMATE_LAST_EXIT", "")).strip()
        try:
            exit_code = int(raw_exit)
        except ValueError:
            exit_code = None
        history = _history_text(config, args)
        context = ShellContext(history=history, last_command=last_command, last_exit_code=exit_code)
        # zsh 没有 postexec 钩子，命令输出在 precmd 执行时已经消失，插件无法事后捕获，
        # 这里能给的只有命令本身、退出码和历史。必须明确告诉模型"没有输出"，否则它会
        # 顺着"解释失败原因"的提问编造一段看起来合理的报错。
        if exit_code == 0:
            question = (
                "解释一下刚才这条命令：它做了什么、有什么副作用或值得注意的地方。"
                "注意：没有捕获到它的输出，不要假定或编造输出内容；如需确认，请给出"
                "获取输出的命令（例如 `cmd 2>&1 | shellmate-ai explain`）。"
            )
        else:
            question = (
                "刚才这条命令失败了，但没有捕获到它的输出，目前只有命令本身和退出码。"
                "请结合退出码说明最可能的原因、还需要哪些输出才能确认，并给出获取该输出的"
                "具体命令（例如 `cmd 2>&1 | shellmate-ai explain`）。不要编造具体的报错内容。"
            )
        _ask(config, question, context, args)
        return

    if args.command == "explain":
        if sys.stdin.isatty():
            print(
                "shellmate-ai: explain 需要管道输入，例如：command 2>&1 | shellmate-ai explain",
                file=sys.stderr,
            )
            raise SystemExit(1)
        output = sys.stdin.read()
        if not output.strip():
            print("shellmate-ai: 标准输入为空。", file=sys.stderr)
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
            question = input("向 Shellmate 提问: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nshellmate-ai: 未输入问题。", file=sys.stderr)
            raise SystemExit(1)
    if not question:
        print("shellmate-ai: 未输入问题。", file=sys.stderr)
        raise SystemExit(1)
    context = read_context(_history_text(config, args))
    _ask(config, question, context, args)


if __name__ == "__main__":
    main()
