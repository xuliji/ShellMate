"""在 shell 内容发往模型或搜索服务前，尽力移除常见凭据。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


class SecretRedactionMiddleware:
    """模型和外部工具请求边界上的脱敏中间件。

    用户提供的 shell 文本会在进入模型或搜索服务之前经过脱敏。
    该处理基于规则尽力识别，无法覆盖所有可能的秘密格式。
    """

    _DEFAULTS = (
        # PEM 私钥可能是多行文本，因此整块替换。
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[PRIVATE KEY REDACTED]"),
        # 覆盖常见云密钥、API 密钥、键值形式的凭据和 Bearer Token。
        (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[AWS ACCESS KEY REDACTED]"),
        (re.compile(r"\b(?:sk|pk)-(?:proj-)?[A-Za-z0-9_-]{16,}\b"), "[API KEY REDACTED]"),
        (re.compile(r"(?i)(\b(?:password|passwd|token|secret|api[_-]?key)\b\s*[=:]\s*)([^\s;&]+)"), r"\1[REDACTED]"),
        (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE), "Bearer [REDACTED]"),
    )

    def __init__(self, enabled: bool = True, custom_patterns: Sequence[str] = ()):
        """加载默认规则，并追加用户配置的正则表达式。"""
        self.enabled = enabled
        self.patterns = list(self._DEFAULTS)
        for pattern in custom_patterns:
            self.patterns.append((re.compile(pattern), "[REDACTED]"))

    def redact(self, text: str) -> str:
        """依次应用规则；关闭脱敏时原样返回文本。"""
        if not self.enabled:
            return text
        for pattern, replacement in self.patterns:
            text = pattern.sub(replacement, text)
        return text

    def before_model(self, value: Any) -> Any:
        """在调用模型前返回经过脱敏的文本或消息副本。"""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, Mapping):
            return {key: self.before_model(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(self.before_model(item) for item in value)
        if isinstance(value, list):
            return [self.before_model(item) for item in value]
        if hasattr(value, "content") and isinstance(value.content, str):
            # LangChain 消息不可变时复制对象，仅替换正文并保留角色与工具调用信息。
            try:
                return value.model_copy(update={"content": self.redact(value.content)})
            except AttributeError:
                return value.__class__(content=self.redact(value.content))
        return value

    def before_tool(self, value: str) -> str:
        """在搜索请求或工具结果进入模型前清理文本。"""
        return self.redact(value)
