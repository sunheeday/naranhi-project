from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import re
import ssl
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse, urlunparse
from xml.etree import ElementTree

import httpx

from app.crawler.http_client import DEFAULT_HEADERS, legacy_ssl_context, make_async_client_for_url

FLAVOR_GYO6_RSS2 = "gyo6_rss2"
FLAVOR_JBEDU_JSON = "jbedu_json"
JBEDU_RSS_HOST = "school.jbedu.kr"
UNSUPPORTED_RECHECK_DAYS = 30


@dataclass(frozen=True)
class RssItem:
    """두 flavor 를 하나로 정규화한 항목. body_html/attachments 는 저장만 하고 소비하지 않는다."""

    title: str
    link: str  # 정규화 후 절대 URL
    published_at: str | None = None
    guid: str | None = None
    body_html: str | None = None
    attachments: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class RssFeedState:
    status: str  # "ok" | "unknown" | "unsupported"
    flavor: str | None
    url: str | None
    board_key: str | None
    item_count: int
    checked_at: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "flavor": self.flavor,
            "url": self.url,
            "board_key": self.board_key,
            "item_count": self.item_count,
            "checked_at": self.checked_at,
            "error": self.error,
        }


def derive_feed_url(*, board_url: str, parser_family: str, board_key: str) -> tuple[str, str] | None:
    """(피드 URL, flavor). 규칙에 맞지 않으면 None.

    새 URL 빌더를 만들지 않는다 — notice_post_extractor 가 이미 만든 board_key 를
    그대로 쓰고 경로만 치환한다.
    """
    host = (urlparse(board_url).hostname or "").lower()

    if parser_family == "select_ntt_like":
        params = dict(
            item.split("=", 1) for item in board_key.split("|") if "=" in item
        )
        mi = (params.get("mi") or "").strip()
        bbs_id = (params.get("bbsId") or "").strip()
        if not mi or not bbs_id or "None" in (mi, bbs_id):
            return None
        feed = urlparse(_feed_path(board_url))
        return (
            urlunparse(
                (feed.scheme, feed.netloc, feed.path, "", urlencode([("mi", mi), ("bbsId", bbs_id)]), "")
            ),
            FLAVOR_GYO6_RSS2,
        )

    # ⚠️ 전북 규칙은 호스트 고정이 필수다. slash_view_like 는 울산(school.use.go.kr)·
    # 충북(school.cbe.go.kr)에서도 잡히는데(notice_post_extractor.py:239) 그 둘은 RSS 가
    # 없다. 호스트 검사 없이 적용하면 매 크롤마다 404 를 한 번씩 때린다.
    if parser_family == "slash_view_like" and host == JBEDU_RSS_HOST:
        segments = [item for item in board_key.split("/") if item]
        if len(segments) != 2:
            return None
        school_id, board_code = segments
        return (f"https://{JBEDU_RSS_HOST}/rss/{school_id}/{board_code}.do", FLAVOR_JBEDU_JSON)

    return None


def _feed_path(board_url: str) -> str:
    """notice_post_extractor._replace_path_suffix(:1340-1343) 와 같은 규칙.

    순환 import(그쪽이 이 모듈을 import 한다)를 피하려고 지역 사본을 둔다.
    """
    parsed = urlparse(board_url)
    path = (
        parsed.path.replace("selectNttList.do", "selectRssFeed.do")
        if "selectNttList.do" in parsed.path
        else parsed.path.rstrip("/") + "/selectRssFeed.do"
    )
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def should_probe(raw: dict[str, Any] | None, *, board_key: str, now: datetime) -> bool:
    """스펙 §4.1 재시도 표."""
    if not isinstance(raw, dict) or not raw.get("status"):
        return True
    if raw.get("board_key") != board_key:
        return True  # 게시판이 바뀌면 저장된 피드 URL 은 다른 게시판을 가리킨다
    status = str(raw.get("status"))
    if status == "ok":
        return False
    if status == "unsupported":
        checked_at = _parse_iso(raw.get("checked_at"))
        if checked_at is None:
            return True
        return now - checked_at >= timedelta(days=UNSUPPORTED_RECHECK_DAYS)
    return True  # unknown 은 일시적 실패로 보고 다음 크롤에서 재프로브


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def relaxed_ssl_context() -> ssl.SSLContext:
    """crawler.http_client.legacy_ssl_context() + OP_LEGACY_SERVER_CONNECT.

    school.jbedu.kr / school.gyo6.net 은 기본 legacy 호스트 목록
    (http_client.DEFAULT_LEGACY_TLS_HOSTS = sen.ms.kr, gen.ms.kr)에 없는데,
    OpenSSL 3 의 unsafe-legacy-renegotiation 제한에서 연결이 끊긴다(WinError 10054).
    공용 호스트 목록·공용 컨텍스트를 바꾸지 않으려고 여기서만 옵션을 얹는다.
    """
    context = legacy_ssl_context()
    option = getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0)
    if option:
        context.options |= option
    return context


async def fetch_feed(url: str, *, timeout: float) -> tuple[int, bytes]:
    """피드 1회 GET. 전송 오류일 때만 완화 컨텍스트로 한 번 더 시도한다."""
    try:
        async with make_async_client_for_url(url=url, timeout=timeout) as client:
            response = await client.get(url)
            return response.status_code, response.content
    except httpx.TransportError:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=DEFAULT_HEADERS,
            verify=relaxed_ssl_context(),
        ) as client:
            response = await client.get(url)
            return response.status_code, response.content


def normalize_rss_link(raw: str, feed_url: str) -> str:
    """스펙 §5.2 규칙 1~5. 경북 생성기 버그(스킴 없음 + 선두 세그먼트 2회 반복) 대응.

    규칙 4(호스트 검사)가 외부 링크·오픈 리다이렉트를 차단한다.
    실패하면 빈 문자열을 돌려주고 그 item 만 버린다 — 크롤은 계속된다.
    """
    value = (raw or "").strip()
    if not value:
        return ""
    feed = urlparse(feed_url)

    # 규칙 1·2 — 스킴/호스트 보정
    if value.startswith("//"):
        value = f"{feed.scheme}:{value}"
    elif value.startswith("/"):
        value = urljoin(f"{feed.scheme}://{feed.netloc}", value)
    elif not urlparse(value).scheme:
        value = f"{feed.scheme}://{value}"

    parsed = urlparse(value)
    if not parsed.netloc:
        return ""

    # 규칙 4 — 피드 호스트와 다르면 버린다
    if (parsed.hostname or "").lower() != (feed.hostname or "").lower():
        return ""

    # 규칙 3 — 선두 세그먼트가 정확히 2회 연속 반복이면 하나 제거.
    # 맹목적 중복 제거가 아니다: 선두에 한정하고 중간의 /na/na/ 는 건드리지 않는다.
    segments = parsed.path.split("/")
    if len(segments) >= 3 and segments[0] == "" and segments[1] and segments[1] == segments[2]:
        segments = [segments[0], *segments[2:]]
    path = "/".join(segments)

    # 규칙 5 — fragment·params 를 떨어내고 끝 슬래시를 없앤다
    # (notice_post_extractor._normalize_url:1371-1373 과 같은 모양).
    return urlunparse((parsed.scheme, parsed.netloc, path.rstrip("/"), "", parsed.query, ""))


def parse_feed(body: bytes, *, flavor: str, feed_url: str) -> list[RssItem]:
    """flavor 별 파싱. 실패하면 예외를 올린다 — 호출부(게이트 2)가 unsupported 로 접는다.

    Content-Type 은 보지 않는다: 전북은 JSON 을 주고 첨부는 octet-stream 을 준다.
    """
    if flavor == FLAVOR_JBEDU_JSON:
        return _parse_jbedu_json(body, feed_url)
    if flavor == FLAVOR_GYO6_RSS2:
        return _parse_rss2(body, feed_url)
    raise ValueError(f"unknown rss flavor: {flavor}")


def _parse_rss2(body: bytes, feed_url: str) -> list[RssItem]:
    root = ElementTree.fromstring(body)
    channel = root.find("channel")
    if channel is None:
        channel = root
    items: list[RssItem] = []
    for node in channel.findall("item"):
        title = _node_text(node, "title")
        link = normalize_rss_link(_node_text(node, "link") or _node_text(node, "guid"), feed_url)
        if not title or not link:
            continue
        attachments = []
        for file_node in node.findall("file"):
            name = _node_text(file_node, "fileNm")
            url = normalize_rss_link(_node_text(file_node, "dwldUrl"), feed_url)
            if name and url:
                attachments.append({"name": name, "url": url})
        items.append(
            RssItem(
                title=title,
                link=link,
                published_at=_node_text(node, "pubDate") or None,
                guid=_node_text(node, "guid") or None,
                body_html=_node_text(node, "description") or None,
                attachments=attachments,
            )
        )
    if not items and channel.find("item") is None and channel is root:
        raise ValueError("rss channel not found")
    return items


def _parse_jbedu_json(body: bytes, feed_url: str) -> list[RssItem]:
    payload = json.loads(body.decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("jbedu rss payload is not an object")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise ValueError("jbedu rss payload has no items[]")

    items: list[RssItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        link = normalize_rss_link(str(raw.get("link") or ""), feed_url)
        if not title or not link:
            continue
        description = raw.get("description")
        body_html = description.get("value") if isinstance(description, dict) else None
        items.append(
            RssItem(
                title=title,
                link=link,
                published_at=str(raw.get("pubDate") or "") or None,
                guid=str(raw.get("guid") or "") or None,
                body_html=str(body_html) if body_html else None,
                attachments=[],
            )
        )
    return items


def _node_text(node: Any, tag: str) -> str:
    child = node.find(tag)
    if child is None:
        return ""
    return " ".join((child.text or "").split())


async def probe_rss_feed(
    *,
    board_url: str,
    parser_family: str,
    board_key: str,
    sample_titles: list[str],
    timeout: float,
) -> RssFeedState:
    """4단 게이트를 **전부** 통과해야 ok 다(스펙 §4.3)."""
    derived = derive_feed_url(board_url=board_url, parser_family=parser_family, board_key=board_key)
    if not derived:
        return _state("unsupported", None, None, board_key, 0, "no_feed_rule")
    feed_url, flavor = derived

    try:
        status_code, body = await fetch_feed(feed_url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - 프로브 실패는 크롤에 영향을 주지 않는다.
        return _state("unknown", flavor, feed_url, board_key, 0, f"fetch_{type(exc).__name__}")

    # 게이트 1 — HTTP 200. 부산·제주·경남의 404/400 을 거른다.
    if status_code != 200:
        return _state("unsupported", flavor, feed_url, board_key, 0, f"http_{status_code}")

    # 게이트 2 — 파싱 성공. 세종처럼 200 에 오류 HTML 을 담는 경우를 거른다.
    # Content-Type 은 신뢰하지 않는다: 전북은 JSON 을 주고 첨부는 octet-stream 을 준다.
    try:
        items = parse_feed(body, flavor=flavor, feed_url=feed_url)
    except Exception:  # noqa: BLE001 - 파싱 실패는 '이 엔드포인트는 RSS 가 아니다' 이다.
        return _state("unsupported", flavor, feed_url, board_key, 0, "parse_failed")

    # 게이트 3 — 비어있지 않음. item 0건은 ok 가 아니라 unknown 이다.
    # 방학 중 빈 게시판과 서울 AJAX 식 '조용한 0건' 을 구분할 수 없기 때문.
    usable = [item for item in items if item.title and (item.link or item.guid)]
    if not usable:
        return _state("unknown", flavor, feed_url, board_key, len(items), "empty_feed")

    # 게이트 4 — 교차검증. 같은 크롤에서 HTML 파서가 뽑은 제목과 교집합 ≥ 1.
    # mi/bbsId 가 다른 게시판(급식·앨범)을 가리키면 여기서 걸린다.
    if sample_titles and not titles_intersect([item.title for item in usable[:5]], sample_titles):
        return _state("unknown", flavor, feed_url, board_key, len(usable), "title_mismatch")

    return _state("ok", flavor, feed_url, board_key, len(usable), None)


def titles_intersect(feed_titles: list[str], sample_titles: list[str]) -> bool:
    """HTML 목록 제목에는 '[가정통신문] … NEW 첨부' 같은 잡음이 섞이므로 포함 관계로 본다."""
    samples = [item for item in (_compact(value) for value in sample_titles) if item]
    for title in feed_titles:
        needle = _compact(title)
        if len(needle) < 4:
            continue
        if any(needle in sample or sample in needle for sample in samples):
            return True
    return False


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").replace("\xa0", " ")).lower()


def _state(
    status: str,
    flavor: str | None,
    url: str | None,
    board_key: str,
    item_count: int,
    error: str | None,
) -> RssFeedState:
    return RssFeedState(
        status=status,
        flavor=flavor,
        url=url,
        board_key=board_key,
        item_count=item_count,
        checked_at=datetime.now(UTC).isoformat(),
        error=error,
    )
