"""학교 홈페이지에서 «일과표(시정표)» 를 찾아 교시별 시각을 뽑는다.

왜 이게 필요한가: NEIS 시간표는 날짜·교시·과목만 주고 시계 시각을 주지 않는다.
하교 시각을 계산하려면 «몇 교시가 몇 시에 끝나는지» 를 학교마다 따로 알아야 한다.

2026-08-30 실측으로 정해진 설계:
- 우리 학교 5곳 중 «일과표» 메뉴가 있는 곳은 1곳뿐이었다(부천부흥중). 초등 3곳은 없었다.
  → 이 경로는 «찾히면 완벽하지만 대개 못 찾는다». 못 찾는 것이 기본값이므로
     실패는 조용히 돌아가고, 학교급 표준값이 계속 쓰인다.
- 찾은 일과표는 «글이 아니라 그림»이었다. 그 페이지의 글자 본문 1,782자에 교시는
  0개였고 시각 4개는 전부 교무실 전화 운영시간(08:40~16:40)이었다.
  → 글에서 못 찾으면 곧바로 본문 이미지를 판독한다.
- 링크 텍스트에 «시정»이 들어간 것 둘은 전부 캐러셀 «일시정지» 버튼이었다.
  → 프롬프트와 필터가 이걸 명시적으로 배제한다.

여기서 뽑은 결과는 confirmed_at=null 로 저장되어 사람 승인을 기다린다.
AI 가 그림을 잘못 읽으면 틀린 하교 시각이 부모에게 알림으로 나가기 때문이다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup

MIN_PERIOD = 1
MAX_PERIOD = 12
# 상식 밖 시각은 판독 실패로 본다.
EARLIEST_MINUTES = 5 * 60
LATEST_MINUTES = 22 * 60
# 한 교시 길이. 초등 40 / 중등 45 / 고등 50 이 표준이고 블록수업이어도 두 배를 넘지 않는다.
MIN_LESSON_MINUTES = 20
MAX_LESSON_MINUTES = 120
# 글자 본문만으로 «일과표다» 라고 단정하는 최소 교시 수.
# 둘로 낮추면 시험 안내문("1교시 국어, 2교시 수학")이 걸린다.
MIN_PERIODS_FOR_TEXT = 3

# 장식 이미지 경로 조각. 실측 홈페이지에서 본문 이미지와 이 이름들로 갈렸다.
_DECORATION_HINTS = (
    "logo", "icon", "btn", "bullet", "banner", "common",
    "blank", "sns", "menuimg", "s_visual", "subimg",
)
# alt/파일명에 이게 있으면 일과표 이미지일 가능성이 높아 앞으로 당긴다.
_BELL_HINTS = ("일과", "시정", "등하교", "수업시간")

_TIME = r"([0-9]{1,2})\s*[:：]\s*([0-9]{2})"
_DASH = r"\s*[~\-–—]\s*"
# "1교시 09:10~09:55" / "1교시 9:10 ~ 9:55"
_KOREAN_ROW = re.compile(rf"([0-9]{{1,2}})\s*교시[^0-9]{{0,6}}{_TIME}{_DASH}{_TIME}")
# "1|09:10|09:55" — 모델에게 요청하는 형식
_PIPE_ROW = re.compile(rf"^\s*([0-9]{{1,2}})\s*\|\s*{_TIME}\s*\|\s*{_TIME}\s*$", re.MULTILINE)


@dataclass(frozen=True)
class BellScheduleResult:
    periods: list[dict]
    source_url: str | None
    note: str


def _mins(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(hour: str | int, minute: str | int) -> str:
    return f"{int(hour):02d}:{int(minute):02d}"


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def parse_bell_text(text: str) -> list[dict]:
    """글자에서 교시별 시각을 뽑는다. 못 뽑으면 빈 리스트(예외 아님).

    «교시» 라는 말이 붙어 있거나 파이프 형식일 때만 잡는다. 그냥 시각 두 개가
    붙어 있는 것(전화 운영시간 등)은 절대 교시로 보지 않는다.
    """
    rows: list[dict] = []
    seen: set[int] = set()

    for m in _PIPE_ROW.finditer(text):
        period = int(m.group(1))
        if period in seen:
            continue
        seen.add(period)
        rows.append({
            "period": period,
            "start_time": _hhmm(m.group(2), m.group(3)),
            "end_time": _hhmm(m.group(4), m.group(5)),
        })

    for m in _KOREAN_ROW.finditer(text):
        period = int(m.group(1))
        if period in seen:
            continue
        seen.add(period)
        rows.append({
            "period": period,
            "start_time": _hhmm(m.group(2), m.group(3)),
            "end_time": _hhmm(m.group(4), m.group(5)),
        })

    return sorted(rows, key=lambda r: r["period"])


def looks_like_bell_table(text: str) -> bool:
    """글자 본문만으로 일과표라 볼 수 있는가."""
    return len(parse_bell_text(text)) >= MIN_PERIODS_FOR_TEXT


def normalize_bell_periods(items: object) -> list[dict]:
    """뽑은 표를 검증한다. 하나라도 이상하면 통째로 버린다(ValueError).

    반쯤 맞는 일과표를 통과시키면 틀린 하교 시각이 부모에게 알림으로 나간다.
    그건 알림이 아예 없는 것보다 나쁘다.
    """
    if isinstance(items, dict):
        items = items.get("periods")
    if not isinstance(items, (list, tuple)) or not items:
        raise ValueError("교시가 비어 있습니다.")

    out: list[dict] = []
    seen: set[int] = set()

    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError(f"교시 항목 형식이 아닙니다: {raw!r}")
        try:
            period = int(raw["period"])
            start = str(raw["start_time"])[:5]
            end = str(raw["end_time"])[:5]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"교시 항목을 읽을 수 없습니다: {raw!r}") from exc

        if not (MIN_PERIOD <= period <= MAX_PERIOD):
            raise ValueError(f"교시 범위를 벗어남: {period}")
        if period in seen:
            raise ValueError(f"교시가 중복됩니다: {period}")
        seen.add(period)

        if not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", start) or not re.fullmatch(r"[0-2][0-9]:[0-5][0-9]", end):
            raise ValueError(f"{period}교시 시각 형식이 올바르지 않습니다: {start}~{end}")

        s, e = _mins(start), _mins(end)
        if s >= e:
            raise ValueError(f"{period}교시 시작이 종료보다 늦습니다: {start}~{end}")
        if not (EARLIEST_MINUTES <= s <= LATEST_MINUTES):
            raise ValueError(f"{period}교시 시각이 상식 밖입니다: {start}")
        if not (MIN_LESSON_MINUTES <= e - s <= MAX_LESSON_MINUTES):
            raise ValueError(f"{period}교시 길이가 상식 밖입니다: {e - s}분")

        out.append({"period": period, "start_time": start, "end_time": end})

    out.sort(key=lambda r: r["period"])

    prev_end = None
    for row in out:
        s = _mins(row["start_time"])
        if prev_end is not None and s < prev_end:
            raise ValueError(f"{row['period']}교시가 앞 교시와 겹칩니다.")
        prev_end = _mins(row["end_time"])

    return out


@dataclass(frozen=True)
class BellLink:
    text: str
    url: str
    is_bell_wording: bool


# 일과표 메뉴가 쓰는 말. «시간표»(요일별 과목 배치)와 «학사일정»(월별 행사)은 다른 것이다.
_BELL_WORDS = ("일과표", "일과 운영", "일과운영", "시정표", "등하교", "수업시간")
# 캐러셀 제어 버튼. 실측에서 «시정» 매칭 둘이 전부 이것이었다.
_NOT_LINKS = ("일시정지", "재생", "이전", "다음")
_SKIP_HREF = ("javascript:", "#", "mailto:", "tel:")


def bell_link_candidates(html: str, base_url: str) -> list[BellLink]:
    """일과표를 찾기 위한 링크 후보.

    link_extractor.extract_links 를 쓰지 않는다. 그쪽은 게시판 탐색용이라 같은 URL 을
    합치면서 «첫» 앵커 텍스트만 남기는데, 실측 부천부흥중에서 일과표 링크가 상위 메뉴
    이름인 '학생마당' 으로 붙어 나왔다. 그 라벨로는 일과표인 줄 알 수 없다.
    여기서는 (텍스트, URL) 쌍을 그대로 보존한다.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[BellLink] = []
    seen: set[tuple[str, str]] = set()

    for anchor in soup.find_all("a"):
        text = " ".join(anchor.get_text(strip=True).split())
        href = (anchor.get("href") or "").strip()
        if not text or not href:
            continue
        if href.startswith(_SKIP_HREF):
            continue
        if any(word in text for word in _NOT_LINKS):
            continue
        if len(text) > 40:
            continue

        url = urljoin(base_url, href)
        key = (text, url)
        if key in seen:
            continue
        seen.add(key)
        out.append(BellLink(text=text, url=url, is_bell_wording=any(w in text for w in _BELL_WORDS)))

    out.sort(key=lambda c: not c.is_bell_wording)
    return out


def content_image_urls(html: str, base_url: str) -> list[str]:
    """본문 이미지 후보를 우선순위 순으로. 장식 이미지는 뺀다."""
    soup = BeautifulSoup(html, "html.parser")
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        url = urljoin(base_url, src)
        if url in seen:
            continue
        low = url.lower()
        if any(hint in low for hint in _DECORATION_HINTS):
            continue
        seen.add(url)

        alt = (img.get("alt") or "")
        blob = f"{alt} {url}"
        # alt 에 «일과표» 같은 힌트가 있으면 먼저 시도한다.
        score = 1 if any(hint in blob for hint in _BELL_HINTS) else 0
        scored.append((score, url))

    scored.sort(key=lambda pair: -pair[0])
    return [url for _, url in scored]


BELL_PAGE_PROMPT = """
너는 한국 학교 홈페이지에서 '일과표(시정표)' 페이지를 찾는 분류기다.

찾는 것:
- 교시별 «시작·종료 시각»이 적힌 페이지. 메뉴 이름은 보통
  일과표 / 시정표 / 일과운영 / 등하교 시간 / 수업시간 이다.

절대 규칙:
- '학사일정'(월별 행사표)은 일과표가 아니다. 고르지 마라.
- '시간표'(요일별 과목 배치)도 일과표가 아니다. 고르지 마라.
- '일시정지'는 캐러셀 제어 버튼이다. 링크가 아니므로 절대 고르지 마라.
- 급식/식단 관련 링크는 고르지 마라.
- 확실하지 않으면 best_url 을 null 로 두고 needs_human_check 를 true 로 둬라.
  못 찾는 것이 정상이다 — 억지로 고르지 마라.
""".strip()

# GeminiDocumentExtractor 는 응답을 JSON 객체로 파싱해 "text" 만 꺼낸다
# (gemini_document_extractor.ocr_prompt 와 같은 규약). 그래서 교시 줄을 그 "text"
# 안에 담게 한다 — 평문으로 시키면 모델이 JSON 배열을 내고 파서가 깨진다(실측).
BELL_IMAGE_PROMPT = """
이 그림은 한국 학교의 일과표(시정표)다. 교시별 시작·종료 시각만 뽑아라.

text 필드에는 아래 형식의 줄만 담는다(설명 문장 금지):
교시번호|시작시각|종료시각

예: "1|09:10|09:55\\n2|10:05|10:50"

규칙:
- 24시간 표기, 반드시 HH:MM.
- '교시'로 표시된 행만 뽑아라. 등교·조회·점심·종례·청소·창체는 제외한다.
- 표에 없는 교시를 지어내지 마라.
- 교시별 시각을 읽을 수 없으면 text 를 빈 문자열로 두고 is_readable=false 로 둬라.

반드시 JSON만 반환한다.
{
  "text": "1|09:10|09:55\\n2|10:05|10:50",
  "confidence": 0.0,
  "is_readable": true,
  "warnings": [],
  "detected_layout": "table",
  "source_pages": [1]
}
""".strip()


async def _choose_page_with_bedrock(
    *,
    school_name: str,
    homepage_url: str,
    candidates: list[BellLink],
) -> str | None:
    """링크 목록에서 일과표 페이지를 고른다. 확실하지 않으면 None.

    Bedrock 으로 부른다 — GCP 지출을 만들지 않는다. 못 찾는 것이 정상이므로
    (실측 5곳 중 4곳) 억지로 고르게 만들지 않는다.
    """
    import json as _json

    from app.core.config import get_settings
    from app.translation.bedrock_client import BedrockJsonClient

    allowed = {c.url for c in candidates}
    listing = _json.dumps(
        [{"text": c.text, "url": c.url} for c in candidates], ensure_ascii=False,
    )
    prompt = (
        f"{BELL_PAGE_PROMPT}\n\n"
        f"학교명: {school_name}\n학교 홈페이지: {homepage_url}\n\n"
        f"후보 링크 JSON:\n{listing}\n\n"
        '반드시 아래 JSON만 반환한다.\n'
        '{"best_url": "https://... 또는 null", "reason": "판단 이유"}'
    )

    settings = get_settings()
    client = BedrockJsonClient(
        model=settings.bedrock_translation_model,
        region=settings.bedrock_region,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_workers=2,
    )
    payload = await client.generate_json(prompt=prompt, temperature=0.0)

    best = payload.get("best_url")
    if not isinstance(best, str) or not best.startswith("http"):
        return None
    # 모델이 후보에 없는 주소를 지어내면 버린다.
    return best if best in allowed else None


class BellScheduleNotFound(Exception):
    """일과표를 못 찾았다. 예외지만 «정상»에 가깝다 — 실측 5곳 중 4곳이 이렇다.
    호출부는 이걸 잡아 표준값을 그대로 쓰게 두어야 한다."""


async def read_bell_image(data: bytes, *, mime_type: str = "image/png") -> list[dict]:
    """일과표 그림에서 교시별 시각을 뽑는다. 검증까지 통과한 것만 돌려준다.

    AWS Bedrock 으로 읽는다 — GCP 지출을 만들지 않는다(사용자 지시).
    실측(2026-08-30): 부천부흥중 실제 일과표에서 Haiku 가 7교시 전부를 정확히 읽었고
    Gemini 판독·사람 판독과 완전히 일치했다. 응답 5.12초.
    """
    from app.core.config import get_settings
    from app.translation.bedrock_client import BedrockJsonClient

    settings = get_settings()
    client = BedrockJsonClient(
        model=settings.bedrock_translation_model,
        region=settings.bedrock_region,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_workers=2,
    )
    payload = await client.generate_json_with_image(
        data=data, mime_type=mime_type, prompt=BELL_IMAGE_PROMPT,
    )
    return normalize_bell_periods(parse_bell_text(str(payload.get("text") or "")))


async def discover_bell_schedule(
    *,
    school_name: str,
    homepage_url: str,
    max_images: int = 3,
) -> BellScheduleResult:
    """홈페이지 → 일과표 페이지 → (글 또는 그림) → 교시별 시각.

    결과는 confirmed_at=null 로 저장되어 사람 승인을 기다려야 한다. 여기서 자동 승인하지
    않는다 — 잘못 읽으면 틀린 하교 시각이 부모에게 알림으로 나간다.
    """
    from app.crawler.homepage_client import HomepageClient
    from app.crawler.http_client import make_async_client_for_url

    client = HomepageClient(timeout=30.0)
    home = await client.fetch(homepage_url, follow_js_redirect=True)

    candidates = bell_link_candidates(home.html, home.final_url)

    # 1) 링크 이름이 대놓고 «일과표»면 AI 를 부르지 않는다. 실측 부천부흥중이 이 경우다.
    target_url = next((c.url for c in candidates if c.is_bell_wording), None)
    how = "메뉴 이름"

    # 2) 없으면 AI 에게 훑게 한다. 못 찾는 것이 정상이므로 억지로 고르지 않는다.
    #    Bedrock 으로 부른다 — GCP 지출을 만들지 않는다(사용자 지시).
    if target_url is None:
        target_url = await _choose_page_with_bedrock(
            school_name=school_name,
            homepage_url=home.final_url,
            candidates=candidates[:60],
        )
        how = "AI 판단"
        if not target_url:
            raise BellScheduleNotFound("일과표 메뉴를 찾지 못했습니다.")

    page = await client.fetch(target_url, follow_js_redirect=True)

    # 1) 글자에서. 실측에서는 여기서 거의 못 찾지만 찾히면 제일 싸다.
    text = visible_text(page.html)
    if looks_like_bell_table(text):
        return BellScheduleResult(
            periods=normalize_bell_periods(parse_bell_text(text)),
            source_url=page.final_url,
            note=f"본문 글자에서 판독 ({how})",
        )

    # 2) 그림에서. 실측 부천부흥중이 이 경로였다(본문 글자에는 교시가 0개였다).
    last_error: Exception | None = None
    for image_url in content_image_urls(page.html, page.final_url)[:max_images]:
        try:
            # 이 호스트가 구형 TLS 를 쓰는지까지 크롤러 설정을 그대로 따른다.
            async with make_async_client_for_url(url=image_url, timeout=30.0) as http:
                response = await http.get(image_url)
                response.raise_for_status()
                periods = await read_bell_image(
                    response.content,
                    mime_type=response.headers.get("content-type", "image/png").split(";")[0],
                )
            return BellScheduleResult(
                periods=periods,
                source_url=image_url,
                note=f"이미지 판독 ({how})",
            )
        except Exception as exc:  # noqa: BLE001 - 다음 이미지를 시도한다
            last_error = exc
            continue

    raise BellScheduleNotFound(
        f"일과표 페이지({page.final_url})에서 교시 시각을 뽑지 못했습니다."
        + (f" 마지막 오류: {type(last_error).__name__}" if last_error else "")
    )

