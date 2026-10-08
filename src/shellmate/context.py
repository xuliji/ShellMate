"""整理 zsh 提供的近期命令历史上下文。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShellContext:
    history: str = ""

    def as_text(self) -> str:
        """将命令历史整理成模型易于阅读的上下文。"""
        return f"Recent commands:\n{self.history or '(none)'}"


def read_context(history: str) -> ShellContext:
    """限制历史长度后封装上下文，避免无关命令挤占模型输入。"""
    return ShellContext(history=history[-8000:])
