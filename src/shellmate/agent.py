"""基于 LangGraph 构建带工具调用和本地 SQLite 会话记忆的 Agent。"""

from __future__ import annotations

from typing import Annotated, Callable, TypedDict

from langchain_core.messages import AIMessage, AIMessageChunk, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from shellmate.config import AGENT_PROMPT_PATH, CHECKPOINT_DB_PATH, AppConfig, ensure_data_dir
from shellmate.context import ShellContext
from shellmate.privacy import SecretRedactionMiddleware
from shellmate.tools.web_search import web_search

def load_system_prompt() -> str:
    """读取用户配置目录的 Agent.md，作为每次模型调用的系统提示词。"""
    try:
        prompt = AGENT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AgentError(f"无法读取系统提示词文件 {AGENT_PROMPT_PATH}：{exc}") from exc
    if not prompt:
        raise AgentError(f"系统提示词文件不能为空：{AGENT_PROMPT_PATH}")
    return prompt


def _stream_text(chunk: AnyMessage) -> str:
    """从流式 chunk 中提取增量文本，供终端实时打印。

    OpenAI 兼容接口流式返回时，正文通常直接是字符串；部分实现会以
    content blocks（``{"type": "text", "text": ...}``）形式返回，这里一并兼容。
    """
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


class AgentState(TypedDict):
    """图内共享状态；add_messages 负责按 ID 合并并追加消息。"""

    messages: Annotated[list[AnyMessage], add_messages]


class AgentError(RuntimeError):
    """Agent 配置、图运行或持久化失败时抛出的异常。"""


class LangGraphAgent:
    """构建模型与工具节点，并按 thread_id 从本地 SQLite 恢复会话。"""

    def __init__(self, config: AppConfig):
        self.config = config
        self._on_token: Callable[[str], None] | None = None
        ensure_data_dir()
        self.privacy = SecretRedactionMiddleware(
            config.privacy.redact_secrets,
            config.privacy.custom_patterns,
            config.privacy.redact_high_entropy,
        )

        @tool
        def search_web(query: str) -> str:
            """使用 DuckDuckGo 网页搜索查询最新信息或软件文档。"""
            return web_search(query, config.search.endpoint)

        self.tools = [search_web]
        if not config.llm.api_key:
            raise AgentError("请在 llm.api_key 中配置密钥，或设置 OPENAI_API_KEY / SHELLMATE_API_KEY。")
        # 所有服务都通过 OpenAI 兼容协议接入；差异只体现在地址、模型和密钥。
        self.model = ChatOpenAI(
            model=config.llm.model,
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            timeout=config.llm.timeout,
        ).bind_tools(self.tools)

    def _load_system_prompt(self, state: AgentState) -> dict[str, list[AnyMessage]]:
        """系统提示词节点：读取 Agent.md 并作为首条消息加入图状态。

        每个 thread 只注入一次；同一会话后续轮次的状态里已有系统提示词时跳过，
        避免重复追加。用户编辑 Agent.md 后，新会话（新 thread）会读取最新内容。
        """
        if any(isinstance(message, SystemMessage) for message in state["messages"]):
            return {}
        return {"messages": [SystemMessage(content=load_system_prompt())]}

    def _call_model(self, state: AgentState) -> dict[str, list[AnyMessage]]:
        """模型节点：在请求边界脱敏，流式调用模型并边生成边回调输出。

        与 ``invoke`` 不同，这里用 ``model.stream`` 逐块消费响应，把增量文本
        交给 ``_on_token`` 回调，同时将各块聚合成一条完整的 ``AIMessage``
        （含 tool_calls）交回图状态，供 ``tools_condition`` 判定是否调用工具。
        """
        safe_messages = self.privacy.before_model(state["messages"])
        full: AIMessageChunk | None = None
        for chunk in self.model.stream(safe_messages):
            text = _stream_text(chunk)
            if text and self._on_token is not None:
                self._on_token(text)
            full = chunk if full is None else full + chunk
        if full is None:
            return {"messages": []}
        # 聚合成普通 AIMessage，保证 LangGraph 与 tools_condition 拿到干净的
        # content 与 tool_calls，而非流式专用的 AIMessageChunk。
        response = AIMessage(
            content=full.content,
            additional_kwargs=full.additional_kwargs,
            response_metadata=full.response_metadata,
            tool_calls=full.tool_calls,
            invalid_tool_calls=full.invalid_tool_calls,
            usage_metadata=full.usage_metadata,
            id=full.id,
        )
        return {"messages": [response]}

    def _wrap_tool_call(self, request, execute):
        """LangGraph 中间件：在工具执行前后对输入与输出脱敏。

        工具输入（如搜索 query）可能含未识别出的秘密，先脱敏再外发到搜索
        服务，避免泄漏给第三方；工具输出则先脱敏再写回状态，避免敏感内容
        被本地 checkpoint 持久化或再次送入模型。
        """
        call = request.tool_call
        args = call.get("args")
        if isinstance(args, dict):
            safe_args = {
                key: self.privacy.before_tool(value) if isinstance(value, str) else value
                for key, value in args.items()
            }
            request = request.override(tool_call={**call, "args": safe_args})
        result = execute(request)
        if isinstance(result, ToolMessage) and isinstance(result.content, str):
            result = result.model_copy(update={"content": self.privacy.before_tool(result.content)})
        return result

    def _build_graph(self, checkpointer: SqliteSaver):
        """连接系统提示词、模型和工具节点，并注入本地 SQLite checkpoint。"""
        graph = StateGraph(AgentState)
        graph.add_node("system_prompt", self._load_system_prompt)
        graph.add_node("assistant", self._call_model)
        graph.add_node("tools", ToolNode(self.tools, wrap_tool_call=self._wrap_tool_call))
        graph.add_edge(START, "system_prompt")
        graph.add_edge("system_prompt", "assistant")
        graph.add_conditional_edges("assistant", tools_condition, {"tools": "tools", END: END})
        graph.add_edge("tools", "assistant")
        return graph.compile(checkpointer=checkpointer)

    def ask(
        self,
        question: str,
        context: ShellContext,
        thread_id: str,
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """用 LangGraph 配置中的 thread_id 恢复并更新本地 shell 会话。

        传入 ``on_token`` 时，模型回答会边生成边回调增量文本，用于终端流式输出。
        """
        self._on_token = on_token
        thread_id = thread_id.strip()
        if not thread_id or len(thread_id) > 128:
            raise AgentError("thread_id 必须为 1 到 128 个字符。")
        graph_config = {"configurable": {"thread_id": thread_id}}
        user_content = f"{context.as_text()}\n\nQuestion: {question}"
        # 脱敏后再写入 LangGraph 状态，避免原始敏感值被 checkpoint 持久化。
        user_content = self.privacy.redact(user_content)
        try:
            # SqliteSaver 会在本地文件中保存同一 thread_id 的跨进程状态。
            with SqliteSaver.from_conn_string(str(CHECKPOINT_DB_PATH)) as checkpointer:
                checkpointer.setup()
                graph = self._build_graph(checkpointer)
                result = graph.invoke(
                    {"messages": [HumanMessage(content=user_content)]},
                    config=graph_config,
                )
        except Exception as exc:
            raise AgentError(f"LangGraph 执行或 SQLite 持久化失败：{exc}") from exc

        last_message = result["messages"][-1]
        content = last_message.content
        if isinstance(content, str):
            return content or "(No response content.)"
        return "\n".join(str(block.get("text", block)) for block in content)
