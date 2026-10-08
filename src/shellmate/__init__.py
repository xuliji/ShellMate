"""Shellmate：面向 shell 的 AI 助手。"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("shellmate-ai")
except PackageNotFoundError:
    # 未通过 pip/uv 安装（如直接运行源码）时回退到占位版本。
    __version__ = "0.1.0"
