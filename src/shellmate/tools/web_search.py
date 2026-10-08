"""Shellmate 自行实现的 DuckDuckGo HTML 网页搜索工具。"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class SearchResult:
    """一条搜索结果的标题、链接和摘要。"""

    title: str
    url: str
    snippet: str


class _DuckDuckGoParser(HTMLParser):
    """从 DuckDuckGo 的轻量 HTML 页面提取自然搜索结果。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._title_href: str | None = None
        self._title_parts: list[str] = []
        self._snippet_depth = 0
        self._snippet_parts: list[str] = []
        self._current_href: str | None = None

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        return set((dict(attrs).get("class") or "").split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        attrs_map = dict(attrs)
        if tag == "a" and "result__a" in classes:
            self._title_href = attrs_map.get("href")
            self._title_parts = []
        if "result__snippet" in classes:
            if self._snippet_depth == 0:
                self._snippet_parts = []
                self._current_href = self._last_result_href()
            self._snippet_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._title_href:
            title = " ".join("".join(self._title_parts).split())
            if title:
                self.results.append(SearchResult(title, self._clean_url(self._title_href), ""))
            self._title_href = None
        if self._snippet_depth and tag in {"a", "div", "td", "span"}:
            self._snippet_depth -= 1
            if self._snippet_depth == 0 and self._current_href:
                snippet = " ".join("".join(self._snippet_parts).split())
                for index in range(len(self.results) - 1, -1, -1):
                    if self.results[index].url == self._current_href and not self.results[index].snippet:
                        previous = self.results[index]
                        self.results[index] = SearchResult(previous.title, previous.url, snippet)
                        break

    def handle_data(self, data: str) -> None:
        if self._title_href is not None:
            self._title_parts.append(data)
        if self._snippet_depth:
            self._snippet_parts.append(data)

    def _last_result_href(self) -> str | None:
        return self.results[-1].url if self.results else None

    @staticmethod
    def _clean_url(url: str) -> str:
        """去掉 DuckDuckGo 跳转包装，返回原始目标 URL。"""
        parsed = urlparse(url)
        if parsed.path == "/l/":
            target = parse_qs(parsed.query).get("uddg", [None])[0]
            if target:
                return target
        return url


def web_search(query: str, endpoint: str, count: int = 5, timeout: float = 15.0) -> str:
    """请求 DuckDuckGo HTML 搜索页并提取结果，不需要搜索 API Key。"""
    query = query.strip()
    if not query:
        return "搜索词不能为空。"
    count = min(max(int(count), 1), 10)
    request = Request(
        endpoint,
        data=urlencode({"q": query}).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; Shellmate/0.1; +https://github.com/)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            html = response.read(2_000_000).decode("utf-8", errors="replace")
    except HTTPError as exc:
        return f"搜索服务返回 HTTP {exc.code}。"
    except (URLError, TimeoutError) as exc:
        return f"无法连接 DuckDuckGo 搜索：{exc.reason if isinstance(exc, URLError) else exc}"

    parser = _DuckDuckGoParser()
    parser.feed(html)
    # 页面可能重复显示同一链接，去重后按搜索引擎给出的顺序返回。
    unique: list[SearchResult] = []
    seen: set[str] = set()
    for result in parser.results:
        if result.url and result.url not in seen:
            seen.add(result.url)
            unique.append(result)
        if len(unique) >= count:
            break
    if not unique:
        return "未解析到搜索结果。搜索页面可能变更，或请求暂时受到限制。"
    return "\n\n".join(
        f"{index}. {result.title}\n{result.url}\n{result.snippet}".rstrip()
        for index, result in enumerate(unique, start=1)
    )
