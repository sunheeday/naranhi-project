from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup


POSITIVE_STRONG = ("가정통신문", "가정통신", "학부모통신문", "학교통신문")
POSITIVE_WEAK = (
    "알림마당",
    "학교소식",
    "학교공지",
    "공지사항",
    "학부모마당",
    "열린마당",
    "학교마당",
    "게시판",
    "소식",
)
URL_HINTS = ("bbs", "board", "notice", "ntt", "selectNtt", "sub", "menu", "m=")
NEGATIVE = ("급식", "채용", "입찰", "사진", "영상", "방과후", "도서관", "행정", "민원", "예산")
DETAIL_MODE_VALUES = {"downpost", "view", "read", "detail", "viewpost"}
DETAIL_QUERY_KEYS = {"dk_id"}


@dataclass(frozen=True)
class LinkCandidate:
    text: str
    url: str
    context: str
    score: int


def page_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)
    return ""


def page_snippet(html: str, max_chars: int = 500) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ", strip=True).split())
    return text[:max_chars]


def extract_links(base_url: str, html: str, limit: int = 120) -> list[LinkCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc
    by_url: dict[str, LinkCandidate] = {}

    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        if _should_skip_candidate_href(base_url, href):
            continue

        absolute_url = urljoin(base_url, href)
        absolute_url, _ = urldefrag(absolute_url)
        parsed = urlparse(absolute_url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if parsed.netloc and parsed.netloc != base_netloc:
            continue

        text_parts = [
            anchor.get_text(" ", strip=True),
            anchor.get("title") or "",
            anchor.get("aria-label") or "",
        ]
        image = anchor.find("img")
        if image:
            text_parts.append(image.get("alt") or "")

        text = " ".join(part for part in text_parts if part).strip()
        context = _nearby_text(anchor)
        score = score_candidate(text=text, url=absolute_url, context=context)

        if score <= 0 and not text:
            continue

        previous = by_url.get(absolute_url)
        candidate = LinkCandidate(text=text or "(텍스트 없음)", url=absolute_url, context=context, score=score)
        if previous is None or candidate.score > previous.score:
            by_url[absolute_url] = candidate

    return sorted(by_url.values(), key=lambda item: item.score, reverse=True)[:limit]


def find_exact_notice_menu_link(base_url: str, html: str) -> LinkCandidate | None:
    soup = BeautifulSoup(html, "html.parser")
    tabbed_board_link = _find_tabbed_notice_board_link(base_url, soup)
    if tabbed_board_link:
        return tabbed_board_link

    search_roots = [
        soup.select_one("#gnb"),
        soup.select_one("#mgnb"),
        soup.select_one("#snb"),
        soup.select_one(".sitemap"),
        soup,
    ]

    best: LinkCandidate | None = None

    for root in search_roots:
        if root is None:
            continue

        for anchor in root.find_all("a"):
            href = (anchor.get("href") or "").strip()
            if _should_skip_candidate_href(base_url, href):
                continue

            text = _anchor_text(anchor)
            normalized_text = normalize_label(text)
            if not is_primary_notice_text(normalized_text):
                continue

            absolute_url = urljoin(base_url, href)
            absolute_url, _ = urldefrag(absolute_url)
            context = _menu_context(anchor)
            candidate = LinkCandidate(
                text=normalized_text,
                url=absolute_url,
                context=context,
                score=1000,
            )

            if best is None:
                best = candidate
                continue

            if _is_primary_notice_candidate(candidate) and not _is_primary_notice_candidate(best):
                best = candidate

        if best:
            return best

    return None


def find_announcement_menu_link(base_url: str, html: str) -> LinkCandidate | None:
    soup = BeautifulSoup(html, "html.parser")
    search_roots = [
        soup.select_one("#gnb"),
        soup.select_one("#mgnb"),
        soup.select_one("#snb"),
        soup.select_one(".sitemap"),
        soup,
    ]

    for root in search_roots:
        if root is None:
            continue

        for anchor in root.find_all("a"):
            href = (anchor.get("href") or "").strip()
            if _should_skip_candidate_href(base_url, href):
                continue

            text = _anchor_text(anchor)
            compact = compact_label(text)
            if compact not in {"공지사항", "학교공지", "학교공지사항"}:
                continue

            absolute_url = urljoin(base_url, href)
            absolute_url, _ = urldefrag(absolute_url)
            return LinkCandidate(
                text=normalize_label(text),
                url=absolute_url,
                context=f"가정통신문 없음 fallback > {_menu_context(anchor)}",
                score=650,
            )

    return None


def _find_tabbed_notice_board_link(base_url: str, soup: BeautifulSoup) -> LinkCandidate | None:
    for tab_anchor in soup.find_all("a"):
        href = (tab_anchor.get("href") or "").strip()
        if not href.startswith("#") or len(href) <= 1:
            continue

        text = _anchor_text(tab_anchor)
        if not is_primary_notice_text(text):
            continue

        tab_panel = soup.find(id=href[1:])
        if not tab_panel:
            continue

        board_anchor = _find_preferred_board_anchor(tab_panel, base_url)
        if not board_anchor:
            continue

        board_href = (board_anchor.get("href") or "").strip()
        if _should_skip_candidate_href(base_url, board_href):
            continue

        absolute_url = urljoin(base_url, board_href)
        absolute_url, _ = urldefrag(absolute_url)
        return LinkCandidate(
            text=normalize_label(text),
            url=absolute_url,
            context=f"메인 탭 게시판 > {normalize_label(text)}",
            score=1000,
        )

    return None


def _find_preferred_board_anchor(tab_panel, base_url: str) -> object | None:
    anchors = [
        anchor
        for anchor in tab_panel.find_all("a")
        if not _should_skip_candidate_href(base_url, (anchor.get("href") or "").strip())
    ]
    if not anchors:
        return None

    for anchor in anchors:
        classes = anchor.get("class") or []
        label = _anchor_text(anchor)
        if "btn_more" in classes and _is_school_or_allowed_external(base_url, anchor) and "교육청" not in label:
            return anchor

    for anchor in anchors:
        label = _anchor_text(anchor)
        if "더보기" in label and _is_school_or_allowed_external(base_url, anchor) and "교육청" not in label:
            return anchor

    for anchor in anchors:
        href = anchor.get("href") or ""
        label = _anchor_text(anchor)
        if "selectNttList" in href and _is_school_or_allowed_external(base_url, anchor) and "교육청" not in label:
            return anchor

    for anchor in anchors:
        label = _anchor_text(anchor)
        if _is_school_or_allowed_external(base_url, anchor) and "교육청" not in label:
            return anchor

    return None


def _is_school_or_allowed_external(base_url: str, anchor) -> bool:
    href = (anchor.get("href") or "").strip()
    absolute_url = urljoin(base_url, href)
    base_netloc = urlparse(base_url).netloc
    target_netloc = urlparse(absolute_url).netloc
    return target_netloc == base_netloc or "schoolbell-e.com" in target_netloc


def _should_skip_candidate_href(base_url: str, href: str) -> bool:
    if not href:
        return True
    lowered = href.lower()
    if href.startswith("#") or lowered.startswith(("javascript:", "mailto:", "tel:")):
        return True

    absolute_url = urljoin(base_url, href)
    parsed = urlparse(absolute_url)
    query = parse_qs(parsed.query)
    mode_values = [value.lower() for value in query.get("mode", [])]
    query_keys = {key.lower() for key in query}
    return (
        any(value in DETAIL_MODE_VALUES for value in mode_values)
        or bool(query_keys & DETAIL_QUERY_KEYS)
        or _is_detail_page_url(parsed)
    )


def _is_detail_page_url(parsed) -> bool:
    path_lower = parsed.path.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[-2].lower() == "view" and path_parts[-1].isdigit():
        return True
    if path_lower.endswith(("selectnttinfo.do", "boardcnts/view.do")):
        return True
    return False


def score_candidate(text: str, url: str, context: str = "") -> int:
    label_haystack = f"{text} {url}"
    score = 0

    if is_primary_notice_text(label_haystack):
        score += 200
    elif is_notice_text(label_haystack):
        score -= 120
    elif is_primary_notice_text(context):
        score += 25

    for keyword in POSITIVE_STRONG:
        if keyword in label_haystack and "교육청" not in compact_label(label_haystack):
            score += 100
    for keyword in POSITIVE_WEAK:
        if keyword in f"{text} {context}":
            score += 20
    for keyword in URL_HINTS:
        if keyword.lower() in label_haystack.lower():
            score += 5
    for keyword in NEGATIVE:
        if keyword in f"{text} {context}":
            score -= 30

    return score


def _nearby_text(anchor) -> str:
    parts: list[str] = []
    parent = anchor.parent
    for _ in range(2):
        if parent is None:
            break
        text = parent.get_text(" ", strip=True)
        if text:
            parts.append(text[:220])
        parent = parent.parent
    return " / ".join(parts)


def _anchor_text(anchor) -> str:
    parts = []
    for value in (
        anchor.get_text(" ", strip=True),
        anchor.get("title") or "",
        anchor.get("aria-label") or "",
    ):
        normalized = normalize_label(value)
        if normalized and normalized not in parts:
            parts.append(normalized)

    image = anchor.find("img")
    if image:
        image_alt = normalize_label(image.get("alt") or "")
        if image_alt and image_alt not in parts:
            parts.append(image_alt)
    return " ".join(part for part in parts if part).strip()


def normalize_label(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def compact_label(value: str) -> str:
    return normalize_label(value).replace(" ", "")


def is_notice_text(value: str) -> bool:
    compact = compact_label(value)
    if "가정통신문" in compact or "가정통신" in compact or "학부모통신문" in compact or "학교통신문" in compact:
        return True
    if "가정" in compact and "통신문" in compact:
        return True
    if "학부모" in compact and "통신문" in compact:
        return True
    if "학교" in compact and "통신문" in compact:
        return True
    return False


def is_primary_notice_text(value: str) -> bool:
    compact = compact_label(value)
    return is_notice_text(value) and "교육청" not in compact


def candidate_priority(candidate: LinkCandidate) -> tuple[int, int]:
    label = normalize_label(candidate.text)
    context = normalize_label(candidate.context)
    combined = f"{label} {context}"
    compact_combined = compact_label(combined)

    if label == "가정통신문":
        return (0, -candidate.score)
    if is_primary_notice_text(label):
        return (1, -candidate.score)
    if is_notice_text(label) and "교육청" not in compact_label(label):
        return (2, -candidate.score)
    if is_primary_notice_text(combined):
        return (3, -candidate.score)
    if is_notice_text(combined) and "교육청" in compact_combined:
        return (9, -candidate.score)
    if is_notice_text(combined):
        return (4, -candidate.score)
    return (10, -candidate.score)


def _menu_context(anchor) -> str:
    labels: list[str] = []
    current = anchor
    for _ in range(4):
        parent_li = current.find_parent("li")
        if parent_li is None:
            break
        direct_anchor = parent_li.find("a", recursive=False)
        if direct_anchor:
            text = _anchor_text(direct_anchor)
            if text and text not in labels:
                labels.append(text)
        current = parent_li
    return " > ".join(reversed(labels))


def _is_primary_notice_candidate(candidate: LinkCandidate) -> bool:
    text = f"{candidate.text} {candidate.context}"
    return is_primary_notice_text(text)

