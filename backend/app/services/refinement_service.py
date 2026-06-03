"""가정통신문 본문 정제(refinement).

추출 파이프라인이 만든 '날것(raw) 원문'을 사용자에게 보여줄 '정제 본문'으로 다듬는다.
프론트가 읽는 notices.original_text 에 이 정제 결과가 들어간다.

핵심 안전장치 = 마스킹:
  표 / URL / 이메일 / 전화 / 시각 / 날짜를 LLM 에 보내기 전에 ⟦T0⟧⟦U0⟧⟦E0⟧⟦P0⟧⟦M0⟧⟦D0⟧
  토큰으로 치환하고, 정제가 끝난 뒤 원문 그대로 복원한다. → LLM 이 이 값들을 물리적으로
  변조/삭제할 수 없다(예: 24→4 숫자 변조, 표 통째 삭제 같은 사고 차단).
LLM 은 외국어 제거 + 인사말/배너/푸터 제거 + 띄어쓰기/줄바꿈 정돈 같은 '안전한 산문 정리'만 한다.
LLM 이 망가지면(공백폭탄/비정상 팽창) deterministic light_clean 으로 폴백해 충실도를 지킨다.

(파일럿 backend/outputs/llm_clean.py 의 검증된 로직을 프로덕션용으로 포팅. 파일 I/O·meta.json 없이
 단일 호출 async 함수로 동작하며, OCR/추출과 같은 Vertex 연결을 재사용한다.)
"""
from __future__ import annotations

import re
from typing import Any


URL_RE = re.compile(r"(?:https?://|www\.)[A-Za-z0-9./:_?=&%#@~+\-]+")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"0\d{1,2}[-)\s]?\d{3,4}[-\s]?\d{4}")
TIME_RE = re.compile(r"\d{1,2}:\d{2}")  # 일정 시각(HH:MM) — LLM 변조 잦음(13:06->13:00)
DATE_RE = re.compile(  # 날짜 — LLM 변조 잦음(2026->6). 연-월-일 묶음을 통째 보호
    r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일(?:\s*\([월화수목금토일]\))?"
    r"|\d{4}\s*년\s*\d{1,2}\s*월"
    r"|\d{4}\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?(?:\s*\([월화수목금토일]\))?"
    r"|\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}"
    r"|\d{1,2}\s*월\s*\d{1,2}\s*일")

LB, RB = "⟦", "⟧"  # 마스킹 토큰 경계(희귀문자라 본문과 충돌 없음)


def _ref_links(ref: str) -> set[str]:
    """원문에서 URL/이메일을 뽑아 정리(붙은 URL 분리 + HWP 필드 junk 제거)."""
    out: set[str] = set()
    for match in URL_RE.finditer(ref):  # 붙은 URL 분리 + HWP 필드 junk 제거(junk는 URL '뒤')
        for piece in re.split(r"(?=https?://)", match.group(0)):
            cleaned = re.split(r"HWP[A-Z_]{4,}", piece)[0].rstrip(".,)】] ")
            if len(cleaned) > 7 and re.match(r"https?://|www\.", cleaned):
                out.add(cleaned)
    for match in EMAIL_RE.finditer(ref):  # 이메일은 junk가 '앞' -> 마지막 HWP토큰 이후만 취함
        email = re.sub(r".*HWP[A-Z_]{4,}", "", match.group(0)).rstrip(".,)】] ")
        if "@" in email and len(email) > 5:
            out.add(email)
    return out


def mask(md: str) -> tuple[str, dict[str, str]]:
    """표/URL/이메일/전화/시각/날짜를 토큰으로 치환. (마스킹본, store) 반환. store: 토큰->원문 정확값."""
    store: dict[str, str] = {}
    counter = [0]

    def put(kind: str, text: str) -> str:
        key = f"{LB}{kind}{counter[0]}{RB}"
        counter[0] += 1
        store[key] = text
        return key

    # 1) 표 블록(연속된 | 줄) 통째로 마스킹 -> LLM이 표를 재생성하다 깨는 사고 차단
    lines, out, i = md.split("\n"), [], 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(put("T", "\n".join(lines[i:j])))
            i = j
        else:
            out.append(lines[i])
            i += 1
    md = "\n".join(out)

    # 2) 이메일 -> URL -> 전화 -> 시각 -> 날짜 순서로 마스킹(겹침 방지)
    md = EMAIL_RE.sub(lambda m: put("E", m.group(0)), md)
    md = URL_RE.sub(lambda m: put("U", m.group(0)), md)
    md = PHONE_RE.sub(lambda m: put("P", m.group(0)), md)
    md = TIME_RE.sub(lambda m: put("M", m.group(0)), md)
    md = DATE_RE.sub(lambda m: put("D", m.group(0)), md)
    return md, store


def unmask(text: str, store: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    """토큰을 원문으로 복원. LLM이 떨군 토큰은 끝에 안전 복원(내용 100% 보존)."""
    dropped: list[tuple[str, str]] = []
    for key, val in store.items():
        if key in text:
            text = text.replace(key, val)
        else:
            dropped.append((key, val))
    tabs = [v for k, v in dropped if k[1] == "T"]
    inls = [v for k, v in dropped if k[1] != "T"]
    if tabs:
        text += "\n\n" + "\n\n".join(tabs)
    if inls:
        text += "\n\n## 관련 정보\n" + "\n".join(f"- {v}" for v in inls)
    # 혹시 남은 토큰 잔재 제거
    text = re.sub(LB + r"[TUEPMD]\d+" + RB, "", text)
    return text, dropped


def degenerate(out: str, src: str) -> bool:
    """LLM degeneration 감지: 공백폭탄(30칸+ 연속) 또는 비정상 팽창.
    크기 인식: 큰 문서(>4000자)는 LLM이 망가지기 쉬워 팽창에 엄격(1.6배) -> 폴백.
    작은 문서는 구조(##·표) 추가로 정상 팽창하므로 관대(2.6배) -> 불필요 폴백 방지."""
    if re.search(r" {30,}", out):
        return True
    limit = 1.6 if len(src) > 4000 else 2.6
    if len(out) > len(src) * limit + 400:
        return True
    return False


def light_clean(md: str) -> str:
    """LLM이 망가질 때의 폴백: LLM 없이 결정적으로 알려진 쓰레기만 제거(충실 100%)."""
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)                                  # 이미지 md
    md = re.sub(r"원본 그림의 크기[:：][^\n]*?\d+\s*pixel(?:[^\n]*?\d+\s*pixel)?", "", md)  # 그림크기 캡션
    md = re.sub(r"원본 그림의 이름[:：]\s*\S+", "", md)                            # 그림이름 캡션
    md = re.sub(r"\*\*==>.*?<==\*\*", "", md)                                     # PDF placeholder
    md = re.sub(r"(?m)^\s*-\s*\d+\s*-\s*$", "", md)                               # 페이지번호 줄
    md = re.sub(LB + r"[TUEPMD]\d+" + RB, "", md)                                  # 토큰 잔재(있을리 없지만)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def _squeeze_spaces(text: str) -> str:
    """잔여 공백폭탄(연속 3칸+)을 한 칸으로 줄인다. 단,
      - 표(| 줄)는 통째로 보존 — 마스킹으로 지킨 원문을 다시 건드리지 않는다.
      - 줄 앞 들여쓰기는 보존 — 중첩 리스트 등 구조를 깨지 않는다.
    즉 '프로즈 내부/끝'의 폭탄만 정리한다. (대형 30칸+ 폭탄은 이미 degenerate→폴백으로 처리됨.)
    """
    out: list[str] = []
    for line in text.split("\n"):
        if line.lstrip().startswith("|"):       # 표 줄: 원문 그대로
            out.append(line)
            continue
        stripped = line.lstrip(" ")
        if not stripped:                         # 공백뿐인 줄 -> 빈 줄
            out.append("")
            continue
        indent = line[: len(line) - len(stripped)]   # 들여쓰기 보존
        out.append((indent + re.sub(r" {3,}", " ", stripped)).rstrip())
    return "\n".join(out)


_SECTION_MARKER_RE = re.compile(r"^([◉□■▣◆●◇▪])\s*(\S.{0,38})$")
# 종결어미/마침표로 끝나면 '문장'이므로 제목으로 올리지 않는다.
_HEADING_STOP = (".", "?", "!", "다", "요", "함", "음", "임", "됨", "죠", "까", "오")

# 게시판 UI 메타데이터 줄(공지 본문 아님). 라벨 뒤에 구분자(공백/콜론)+값이 있는 짧은 줄.
_BOARD_META_RE = re.compile(
    r"\s*(작성자|작성일|등록일|게시일|수정일|조회수|조회|추천|댓글|좋아요)(\s*[:：]|\s+)\s*\S"
)
# 라벨만 단독으로 있는 줄(값은 다음 줄에). 게시판이 라벨/값을 줄로 분리해 뽑는 경우.
_BOARD_META_LABELS = frozenset(
    {"작성자", "작성일", "등록일", "게시일", "수정일", "조회수", "조회", "추천", "댓글", "좋아요"}
)


def _strip_board_meta(text: str) -> str:
    """게시판 메타데이터(작성자/작성일/조회수/댓글)를 제거한다 — 같은 줄/여러 줄 형식 모두.

    공지 '본문'이 아니라 게시판 화면 정보라 불필요(특히 본문이 게시판 텍스트뿐일 때 이것만 남는
    사고 방지). 라벨 뒤 구분자가 있는 짧은 줄(`작성자 김**`), 그리고 라벨만 있는 줄+다음 값 줄
    (`작성자`⏎`김**`)을 지운다. '작성자의 의견은…'처럼 구분자 없는 실제 문장은 보존한다.
    """
    lines = text.split("\n")
    kept: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped in _BOARD_META_LABELS:  # 라벨만 있는 줄 -> 라벨 + 값(다음 줄) 함께 제거
            i += 2
            continue
        if len(stripped) <= 40 and _BOARD_META_RE.match(lines[i]):  # 같은 줄형 `작성자 김**`
            i += 1
            continue
        kept.append(lines[i])
        i += 1
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _promote_section_headings(text: str) -> str:
    """'◉ 질병결석' 같은 섹션 표시줄을 결정론적으로 '### …' 제목으로 올린다(LLM 무관·항상 일정).

    LLM 정제는 매번 제목(#)을 붙였다 말았다 들쭉날쭉하므로, 정제 맨 끝에 이 단계를 둬서
    섹션 구조를 일정하게 보장한다. 표(| 줄)·기존 제목(#)·노트(※)·리스트(-)는 건드리지 않고,
    문장형(마침표/종결어미로 끝남)도 제외해 오탐을 막는다.
    """
    out: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(("|", "#")):
            out.append(line)
            continue
        if _SECTION_MARKER_RE.match(stripped) and not stripped.endswith(_HEADING_STOP):
            out.append(f"### {stripped}")
        else:
            out.append(line)
    return "\n".join(out)


PROMPT = f"""너는 학교 가정통신문 '본문 정리기'다. 아래는 문서에서 자동 추출된 markdown이다.

[가장 중요한 규칙 — 마스킹 토큰]
본문에 {LB}T0{RB} {LB}U0{RB} {LB}E0{RB} {LB}P0{RB} {LB}M0{RB} {LB}D0{RB} 처럼 ⟦…⟧ 로 감싼 토큰이 있다.
이것은 표/URL/이메일/전화번호/시각/날짜의 '자리표시자'다. 절대 지우거나, 번역하거나, 번호를 바꾸거나,
내용을 추측해 채우지 마라. 있는 그대로(⟦T0⟧ 형태 그대로) 적절한 위치에 남겨둬라.

[정리 규칙]
1. [충실도-절대] 토큰 밖의 글자·숫자·날짜·금액·고유명사·맞춤법도 절대 바꾸지 마라. 원문의 오타도 그대로 둬라(예: '영키피플'을 '잉키피플'로 고치지 마라). 원문에 없는 문장·설명·배경·해석을 절대 새로 추가하지 마라(할루시네이션 금지).
2. [한국어만] 한국어 본문만 남겨라. 러시아어·영어·중국어·베트남어 등 외국어로 된 번역문·문장·문단은 모두 제거하라. (단, 마스킹 토큰 ⟦…⟧, 그리고 기관·지명·학교의 영문 고유명칭처럼 번역 불가한 짧은 표기는 그대로 둔다.)
3. [본문만] 다음만 제거 가능: 로고/슬로건/교훈, 의례적 인사말("안녕하십니까…기원합니다"), 푸터(공익제보센터 등), 게시판 메타(작성자/조회수/목록/다운로드), 페이지번호(- 1 -), 빈 서식칸. 단, 학교명·발행일·발신자(…장/서명)·일정·연락처·서식 안 실제 안내는 반드시 보존.
4. [구조] 제목은 #, 소제목은 ##, 항목은 - 리스트로 읽기 좋게. 표 형태의 자료는 markdown 표(| |)로 보기 좋게 만들되, 각 값을 원래 행·열 위치에 정확히 배치하고 값을 임의로 섞거나 빠뜨리지 마라. 같은 문단/내용이 원문에서 2번 이상 반복되면 1번만 남겨라. 토큰(⟦…⟧)은 원래 자리 부근에 그대로.
5. [정돈] 띄어쓰기·줄바꿈만 자연스럽게. 깨진 음절 사이 공백은 붙여라.
6. [출력] 정돈된 markdown 본문만. 너의 설명·머리말·코드펜스 없이 본문만.

[추출 markdown]
"""


async def refine(raw_text: str, *, gemini: Any) -> tuple[str, str, int]:
    """원문을 마스킹→LLM 정제→복원한다.

    반환: (정제본, tag, gemini_호출수)
      tag = ok / retry / drop<N> / FALLBACK / empty
      gemini_호출수 = 0(빈입력)·1(정상)·2(재시도 또는 폴백)

    gemini: GeminiDocumentExtractor 인스턴스(추출과 같은 Vertex 연결 재사용).
            .generate_text(prompt) -> str 를 제공해야 한다.
    """
    src = raw_text or ""
    if not src.strip():
        return src, "empty", 0

    masked, store = mask(src)
    calls = [0]

    async def _gen() -> tuple[str, list[tuple[str, str]]]:
        calls[0] += 1
        raw = await gemini.generate_text(PROMPT + masked)
        out = (raw or "").strip()
        out = re.sub(r"^```[a-zA-Z]*\n", "", out)  # 코드펜스 제거
        out = re.sub(r"\n```$", "", out).strip()
        return unmask(out, store)

    out, dropped = await _gen()
    tag = "ok"
    if degenerate(out, src):                       # 공백폭탄/팽창 -> 1회 재시도
        out2, dropped2 = await _gen()
        if not degenerate(out2, src):
            out, dropped, tag = out2, dropped2, "retry"
        else:                                      # 그래도 망가지면 결정적 경량정리 폴백(충실 최우선)
            out, dropped, tag = light_clean(src), [], "FALLBACK"
    if dropped and tag == "ok":
        tag = f"drop{len(dropped)}"

    # 잔여 공백폭탄 정리: 표(| 줄)·들여쓰기는 보존하고 프로즈 내부 3칸+ 연속 공백만 한 칸으로.
    # (표는 마스킹으로 지킨 원문이라 절대 안 건드림. 30칸+ 대형 폭탄은 위에서 degenerate→폴백 처리됨.)
    out = _squeeze_spaces(out)

    # URL/이메일 안전망: 원문에 있던 링크가 빠졌으면 자동 복원
    missing = [u for u in sorted(_ref_links(src)) if u not in out]
    if missing:
        out += "\n\n## 관련 링크\n" + "\n".join(f"- {u}" for u in missing)

    # 게시판 메타(작성자/조회수/댓글) 제거 → 섹션 표시줄(◉ …)을 ### 제목으로 승격(둘 다 결정론적).
    out = _strip_board_meta(out)
    out = _promote_section_headings(out)
    return out, tag, calls[0]
