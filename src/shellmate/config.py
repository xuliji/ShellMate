"""用 Pydantic 定义、读取并校验 Shellmate 的 JSON 配置。"""

from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from shellmate.zsh_plugin import ZSH_PLUGIN

CONFIG_PATH = Path("~/.config/shellmate/config.json").expanduser()
AGENT_PROMPT_PATH = CONFIG_PATH.parent / "Agent.md"
DATA_DIR = CONFIG_PATH.parent / "data"
CHECKPOINT_DB_PATH = DATA_DIR / "checkpoints.sqlite"
ZSH_PLUGIN_PATH = CONFIG_PATH.parent / "shellmate.zsh"
ZSHRC_PATH = Path("~/.zshrc").expanduser()

# 写入 ~/.zshrc 的 source 行，用于幂等判断。
ZSHRC_SOURCE_LINE = "source ~/.config/shellmate/shellmate.zsh"

DEFAULT_AGENT_PROMPT_PACKAGE_PATH = ("prompts", "Agent.md")


def _load_default_agent_prompt() -> str:
    """读取包内数据文件中的默认系统提示词。

    提示词与代码分离，``prompts/Agent.md`` 是唯一来源，并随 wheel/sdist 一起分发；
    这样仓库里维护的内容和用户 ``init`` 得到的模板永远一致。
    """
    try:
        text = files("shellmate").joinpath(*DEFAULT_AGENT_PROMPT_PACKAGE_PATH).read_text(encoding="utf-8")
    except (OSError, ModuleNotFoundError) as exc:  # pragma: no cover - 打包缺失时才触发
        raise ValueError(f"无法读取内置默认系统提示词 prompts/Agent.md：{exc}") from exc
    if not text.strip():
        raise ValueError("内置默认系统提示词 prompts/Agent.md 不能为空")
    return text if text.endswith("\n") else f"{text}\n"


# 首次初始化写入 ~/.config/shellmate/Agent.md 的默认内容。
DEFAULT_AGENT_PROMPT = _load_default_agent_prompt()


def _create_default_config(path: Path) -> None:
    """首次启动时创建配置目录和一份可编辑的默认配置模板。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # thread_id 由 zsh 会话或 CLI 参数提供，不暴露给普通用户配置。
    default_config = AppConfig().model_dump(mode="json", exclude={"thread_id"})
    # JSON 中的空密钥需要用户按需填写，其他字段均可直接使用默认值。
    rendered = json.dumps(default_config, ensure_ascii=False, indent=2) + "\n"
    try:
        # 使用独占创建，避免并发启动时覆盖用户刚写入的配置。
        with path.open("x", encoding="utf-8") as stream:
            stream.write(rendered)
        path.chmod(0o600)
    except FileExistsError:
        # 另一个 Shellmate 进程已先完成初始化，保留它创建的文件。
        pass


def _create_default_agent_prompt(path: Path) -> None:
    """首次启动时创建可由用户直接编辑的系统提示词文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(DEFAULT_AGENT_PROMPT)
        path.chmod(0o600)
    except FileExistsError:
        # 保留用户已编辑的提示词文件。
        pass


def ensure_data_dir() -> None:
    """创建本地 SQLite 数据目录，不要求用户部署数据库服务。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.chmod(0o700)


def ensure_zsh_plugin() -> bool:
    """把 zsh 插件写入配置目录，并在 ~/.zshrc 中幂等地加入 source 行。

    返回 True 表示本次新增了 source 行（需要重载 ~/.zshrc 才生效）。
    """
    ZSH_PLUGIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    ZSH_PLUGIN_PATH.write_text(ZSH_PLUGIN, encoding="utf-8")
    ZSH_PLUGIN_PATH.chmod(0o644)
    try:
        existing = ZSHRC_PATH.read_text(encoding="utf-8")
    except OSError:
        existing = ""
    if ZSHRC_SOURCE_LINE in existing:
        return False
    new = existing
    if new and not new.endswith("\n"):
        new += "\n"
    new += f"\n# Shellmate: 加载 zsh 插件（由 shellmate-ai init 自动添加）\n{ZSHRC_SOURCE_LINE}\n"
    ZSHRC_PATH.write_text(new, encoding="utf-8")
    return True


class StrictSettings(BaseModel):
    """拒绝未知字段，避免配置拼写错误被静默忽略。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class LLMSettings(StrictSettings):
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    timeout: float = Field(default=60.0, gt=0, le=600)

    @field_validator("base_url")
    @classmethod
    def clean_base_url(cls, value: str) -> str:
        return value.strip().rstrip("/")


class ShellSettings(StrictSettings):
    history_lines: int = Field(default=20, ge=1, le=500)


class SearchSettings(StrictSettings):
    endpoint: str = "https://html.duckduckgo.com/html/"

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_be_http(cls, value: str) -> str:
        value = value.strip()
        if not value.startswith(("https://", "http://")):
            raise ValueError("search.endpoint 必须是 HTTP 或 HTTPS URL")
        return value


class PrivacySettings(StrictSettings):
    redact_secrets: bool = True
    redact_high_entropy: bool = True
    custom_patterns: tuple[str, ...] = ()


class AppConfig(StrictSettings):
    """完整应用配置；thread_id 仅作为非 zsh 调用时的内部兜底值。"""

    llm: LLMSettings = Field(default_factory=LLMSettings)
    shell: ShellSettings = Field(default_factory=ShellSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    privacy: PrivacySettings = Field(default_factory=PrivacySettings)
    thread_id: str = "shellmate-cli-default"

    @field_validator("thread_id")
    @classmethod
    def valid_thread_id(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value) > 128:
            raise ValueError("thread_id 必须为 1 到 128 个字符")
        return value


def _apply_environment(raw: dict[str, Any]) -> dict[str, Any]:
    """把支持的环境变量覆盖进配置字典，再交给 Pydantic 统一校验。"""
    data = json.loads(json.dumps(raw))
    llm = data.setdefault("llm", {})
    if not isinstance(llm, dict):
        return data  # 保留错误类型，让 Pydantic 给出准确的字段校验错误。
    key_env = "OPENAI_API_KEY"
    llm["api_key"] = os.getenv("SHELLMATE_API_KEY", os.getenv(key_env, llm.get("api_key", "")))
    llm["base_url"] = os.getenv("SHELLMATE_BASE_URL", llm.get("base_url") or LLMSettings().base_url)
    llm["model"] = os.getenv("SHELLMATE_MODEL", llm.get("model") or LLMSettings().model)

    data["thread_id"] = os.getenv("SHELLMATE_THREAD_ID", data.get("thread_id", "shellmate-cli-default"))
    search = data.setdefault("search", {})
    if not isinstance(search, dict):
        return data
    search["endpoint"] = os.getenv(
        "SHELLMATE_SEARCH_ENDPOINT",
        search.get("endpoint", SearchSettings().endpoint),
    )
    return data


def load_config(path: Path | str = CONFIG_PATH) -> AppConfig:
    """读取并校验 JSON 配置；首次启动时先创建默认配置模板。"""
    path = Path(path).expanduser()
    raw: dict[str, Any] = {}
    if not path.exists():
        try:
            _create_default_config(path)
        except OSError as exc:
            raise ValueError(f"无法创建默认配置文件 {path}：{exc}") from exc
    try:
        _create_default_agent_prompt(path.parent / "Agent.md")
    except OSError as exc:
        raise ValueError(f"无法创建默认系统提示词文件：{exc}") from exc
    with path.open(encoding="utf-8") as stream:
        loaded = json.load(stream)
    if not isinstance(loaded, dict):
        raise ValueError(f"配置文件顶层必须是 JSON 对象：{path}")
    raw = loaded
    try:
        return AppConfig.model_validate(_apply_environment(raw))
    except ValidationError as exc:
        raise ValueError(f"配置校验失败：\n{exc}") from exc
