"""整理 zsh 提供的近期命令历史上下文。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# zsh 开启 EXTENDED_HISTORY 时，历史行形如 `: 1720000000:0;command`。
_EXTENDED_HISTORY_PREFIX = re.compile(r"^: \d+:\d+;")


@dataclass(frozen=True)
class ShellContext:
    history: str = ""
    output: str = ""
    last_command: str = ""
    last_exit_code: int | None = None

    def as_text(self) -> str:
        """将历史、管道输出和上一条命令整理成模型易于阅读的上下文。"""
        parts: list[str] = []
        if self.last_command:
            if self.last_exit_code == 0:
                status = "succeeded"
            elif self.last_exit_code is None:
                status = "unknown exit code"
            else:
                status = f"failed (exit code {self.last_exit_code})"
            parts.append(f"Last command {status}:\n{self.last_command}")
        if self.output:
            parts.append(f"Command output:\n{self.output}")
        parts.append(f"Recent commands:\n{self.history or '(none)'}")
        return "\n\n".join(parts)


def read_context(history: str) -> ShellContext:
    """限制历史长度后封装上下文，避免无关命令挤占模型输入。"""
    return ShellContext(history=history[-8000:])


def read_zsh_history(limit: int) -> str:
    """从 zsh 历史文件读取最近命令，作为直接运行 CLI 时的兜底上下文。

    zsh 插件会通过 ``--history`` 传入当前会话历史；直接运行 ``shellmate-ai ask``
    时没有该数据，这里退而读取历史文件。仅包含已落盘的命令，可能滞后于
    当前交互会话（尚未写入 HISTFILE 的命令不会出现）。
    """
    histfile = Path(os.environ.get("HISTFILE") or Path.home() / ".zsh_history").expanduser()
    try:
        lines = histfile.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    commands = [_EXTENDED_HISTORY_PREFIX.sub("", line) for line in lines[-limit:]]
    return "\n".join(commands)
