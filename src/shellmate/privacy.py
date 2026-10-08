"""在 shell 内容发往模型或搜索服务前，尽力移除常见凭据。

内置规则融合了常见密钥格式，并借鉴 gitleaks / detect-secrets 的思路：

- 已知前缀的 token（GitHub、GitLab、Slack、Stripe、Google、AWS、npm、PyPI 等）；
- 高熵值字符串（Shannon 熵），用于捕获无固定前缀的 API key；
- 键值赋值（``KEY=value``、``--token value`` 等）中的秘密值。
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

# 已知密钥前缀，命中几乎必然是凭据（高置信、低误报）。
_PREFIX_PATTERNS = (
    # GitHub personal access tokens
    (re.compile(r"\bgh[opsu]_[A-Za-z0-9]{36}\b"), "[GITHUB TOKEN REDACTED]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}\b"), "[GITHUB TOKEN REDACTED]"),
    # GitLab / npm / PyPI / Slack
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"), "[GITLAB TOKEN REDACTED]"),
    (re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"), "[NPM TOKEN REDACTED]"),
    (re.compile(r"\bpypi-AgEIc[A-Za-z0-9_\-]{50,}\b"), "[PYPI TOKEN REDACTED]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), "[SLACK TOKEN REDACTED]"),
    # Google / Stripe / SendGrid / Mailgun / AWS
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[GOOGLE API KEY REDACTED]"),
    (re.compile(r"\bya29\.[0-9A-Za-z_\-]{20,}\b"), "[GOOGLE TOKEN REDACTED]"),
    (re.compile(r"\b(?:sk|rk|pk)_(?:test|live)_[A-Za-z0-9]{16,}\b"), "[STRIPE KEY REDACTED]"),
    (re.compile(r"\bSG\.[A-Za-z0-9_\-]{20,}\b"), "[SENDGRID TOKEN REDACTED]"),
    (re.compile(r"\bkey-[A-Za-z0-9]{32}\b"), "[MAILGUN KEY REDACTED]"),
    (re.compile(r"\bASIA[0-9A-Z]{16}\b"), "[AWS ACCESS KEY REDACTED]"),
    # JWT（三段式，头部固定以 eyJ 开头）
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b"), "[JWT REDACTED]"),
)

# 秘密关键词片段：既匹配独立单词（token、secret…），也匹配变量名中的片段
# （如 SOME_TOKEN、DB_PASSWORD、AWS_ACCESS_KEY）。用 \w* 包裹以覆盖下划线连接。
_SECRET_KEYWORD = (
    r"token|secret|password|passwd|credential|apikey"
    r"|api[_-]?key|access[_-]?key|private[_-]?key"
)
_SECRET_KEYWORD_RE = re.compile(rf"\b\w*(?:{_SECRET_KEYWORD})\w*\b", re.IGNORECASE)

# 高熵 token 匹配：至少 20 个连续 token 字符，用于捕获无固定前缀的密钥。
_HIGH_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9+/_\-]{20,}")

# 熵阈值（bit/字符）。高于该值视为接近随机（密钥特征），低于则更像人类可读文本。
_ENTROPY_THRESHOLD = 4.0


def _shannon_entropy(value: str) -> float:
    """计算字符串的 Shannon 熵（bit/字符），用于识别接近随机的密钥。"""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


class SecretRedactionMiddleware:
    """模型和外部工具请求边界上的脱敏中间件。

    用户提供的 shell 文本会在进入模型或搜索服务之前经过脱敏。
    该处理基于规则尽力识别，无法覆盖所有可能的秘密格式。
    """

    _DEFAULTS = (
        # PEM 私钥可能是多行文本，因此整块替换。
        (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[PRIVATE KEY REDACTED]"),
        # 常见云密钥与 Bearer Token（保留 \b 精确边界，避免误伤变量名）。
        (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[AWS ACCESS KEY REDACTED]"),
        (re.compile(r"\b(?:sk|pk)-(?:proj-)?[A-Za-z0-9_-]{16,}\b"), "[API KEY REDACTED]"),
        (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE), "Bearer [REDACTED]"),
        # 键值赋值：KEY=value / KEY: value，其中 KEY 含秘密关键词（独立词或变量名片段）。
        (re.compile(rf"(?i)(\b\w*(?:{_SECRET_KEYWORD})\w*\b\s*[=:]\s*)([^\s;&]+)"), r"\1[REDACTED]"),
    )

    def __init__(
        self,
        enabled: bool = True,
        custom_patterns: Sequence[str] = (),
        redact_high_entropy: bool = True,
    ):
        """加载默认规则，并追加用户配置的正则表达式。"""
        self.enabled = enabled
        self.redact_high_entropy = redact_high_entropy
        self.patterns = list(self._DEFAULTS)
        self.patterns.extend(_PREFIX_PATTERNS)
        for pattern in custom_patterns:
            self.patterns.append((re.compile(pattern), "[REDACTED]"))

    def _redact_high_entropy_tokens(self, text: str) -> str:
        """替换高熵且靠近秘密关键词的 token，捕获无固定前缀的密钥。

        为避免把命令里的哈希、UUID 误判为密钥，仅当 token 所在行出现秘密
        关键词时才替换。
        """
        if not self.redact_high_entropy:
            return text
        lines = text.split("\n")
        for index, line in enumerate(lines):
            if not _SECRET_KEYWORD_RE.search(line):
                continue
            lines[index] = _HIGH_ENTROPY_TOKEN.sub(
                lambda match: (
                    "[HIGH-ENTROPY TOKEN REDACTED]"
                    if _shannon_entropy(match.group(0)) >= _ENTROPY_THRESHOLD
                    else match.group(0)
                ),
                line,
            )
        return "\n".join(lines)

    def redact(self, text: str) -> str:
        """依次应用规则；关闭脱敏时原样返回文本。"""
        if not self.enabled:
            return text
        for pattern, replacement in self.patterns:
            text = pattern.sub(replacement, text)
        return self._redact_high_entropy_tokens(text)

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
