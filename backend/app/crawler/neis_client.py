from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


NEIS_BASE_URL = "https://open.neis.go.kr/hub"
ALLOWED_LEVELS = {"초등학교", "중학교"}

QUOTA_EXCEEDED_CODE = "ERROR-337"
BENIGN_RESULT_CODES = {"INFO-000", "INFO-200"}


class NeisApiError(RuntimeError):
    """NEIS가 HTTP 200 본문에 담아 보낸 오류."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"NEIS {code}: {message}")
        self.code = code
        self.message = message


class NeisQuotaExceeded(NeisApiError):
    """일일 호출 한도 초과(ERROR-337). 한도 값은 공식적으로 미공개다."""


def check_result_code(payload: dict[str, Any], key: str) -> None:
    """행 추출 **앞단**에서 RESULT.CODE를 판정한다.

    NEIS는 오류를 HTTP 상태가 아니라 200 본문의 RESULT 블록으로 돌려준다.
    이 판정이 없으면 ERROR-337(한도 초과)이 빈 배열이 되어 화면에는
    '급식 정보 없음'으로 표시된다.
    """
    code, message = _result_code(payload, key)
    if not code or code in BENIGN_RESULT_CODES:
        return
    if code == QUOTA_EXCEEDED_CODE:
        raise NeisQuotaExceeded(code, message)
    raise NeisApiError(code, message)


def _result_code(payload: dict[str, Any], key: str) -> tuple[str, str]:
    top = payload.get("RESULT")
    if isinstance(top, dict):
        return str(top.get("CODE") or "").strip(), str(top.get("MESSAGE") or "")

    blocks = payload.get(key)
    if isinstance(blocks, list):
        for block in blocks:
            if not isinstance(block, dict):
                continue
            head = block.get("head")
            if not isinstance(head, list):
                continue
            for item in head:
                if isinstance(item, dict) and isinstance(item.get("RESULT"), dict):
                    result = item["RESULT"]
                    return str(result.get("CODE") or "").strip(), str(result.get("MESSAGE") or "")
    return "", ""


@dataclass(frozen=True)
class School:
    name: str
    level: str
    office_code: str
    school_code: str
    address: str
    homepage_url: str


def expand_school_query(query: str) -> list[str]:
    normalized = query.strip()
    if not normalized:
        return []

    candidates = [normalized]

    if normalized.endswith("초") and not normalized.endswith("초등학교"):
        candidates.append(f"{normalized[:-1]}초등학교")
        candidates.append(f"{normalized}등학교")
    if normalized.endswith("중") and not normalized.endswith("중학교"):
        candidates.append(f"{normalized[:-1]}중학교")
        candidates.append(f"{normalized}학교")

    deduped: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def normalize_homepage_url(raw_url: str | None) -> str:
    if not raw_url:
        return ""

    value = raw_url.strip()
    if not value:
        return ""

    if value in {"http:", "https:", "http://", "https://"}:
        return ""

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        if not parsed.netloc:
            return ""
        return value.rstrip("/")

    if value.startswith("//"):
        return f"https:{value}".rstrip("/")

    parsed = urlparse(value)
    if not parsed.scheme:
        return f"https://{value}".rstrip("/")

    if not parsed.netloc:
        return ""

    return value.rstrip("/")


def _extract_rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    check_result_code(payload, key)
    blocks = payload.get(key)
    if not isinstance(blocks, list):
        return []

    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("row"), list):
            return block["row"]
    return []


class NeisClient:
    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    async def get_school_by_codes(
        self,
        office_code: str,
        school_code: str,
    ) -> School | None:
        if not self.api_key:
            raise RuntimeError("NEIS_API_KEY 환경변수가 필요합니다.")

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(
                f"{NEIS_BASE_URL}/schoolInfo",
                params={
                    "KEY": self.api_key,
                    "Type": "json",
                    "pIndex": "1",
                    "pSize": "10",
                    "ATPT_OFCDC_SC_CODE": office_code,
                    "SD_SCHUL_CODE": school_code,
                },
            )
            response.raise_for_status()
            rows = _extract_rows(response.json(), "schoolInfo")

        for row in rows:
            school = _school_from_row(row)
            if school and school.office_code == office_code and school.school_code == school_code:
                return school
        return None

    async def search_schools(self, query: str) -> list[School]:
        if not self.api_key:
            raise RuntimeError("NEIS_API_KEY 환경변수가 필요합니다.")

        found: dict[tuple[str, str], School] = {}

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for school_name in expand_school_query(query):
                params = {
                    "KEY": self.api_key,
                    "Type": "json",
                    "pIndex": "1",
                    "pSize": "100",
                    "SCHUL_NM": school_name,
                }
                response = await client.get(f"{NEIS_BASE_URL}/schoolInfo", params=params)
                response.raise_for_status()
                rows = _extract_rows(response.json(), "schoolInfo")

                for row in rows:
                    school = _school_from_row(row)
                    if not school:
                        continue
                    if not school.homepage_url:
                        continue
                    found[(school.office_code, school.school_code)] = school

        return _rank_schools(query, list(found.values()))


def _school_from_row(row: dict[str, Any]) -> School | None:
    level = str(row.get("SCHUL_KND_SC_NM") or "").strip()
    if level not in ALLOWED_LEVELS:
        return None

    office_code = str(row.get("ATPT_OFCDC_SC_CODE") or "").strip()
    school_code = str(row.get("SD_SCHUL_CODE") or "").strip()
    if not office_code or not school_code:
        return None

    return School(
        name=str(row.get("SCHUL_NM") or "").strip(),
        level=level,
        office_code=office_code,
        school_code=school_code,
        address=str(row.get("ORG_RDNMA") or "").strip(),
        homepage_url=normalize_homepage_url(row.get("HMPG_ADRES")),
    )


def _rank_schools(query: str, schools: list[School]) -> list[School]:
    normalized = query.strip()

    def score(school: School) -> tuple[int, str]:
        name = school.name
        if name == normalized:
            return (0, name)
        if normalized.endswith("초") and name == f"{normalized[:-1]}초등학교":
            return (1, name)
        if normalized.endswith("중") and name == f"{normalized[:-1]}중학교":
            return (1, name)
        if normalized in name:
            return (2, name)
        return (3, name)

    return sorted(schools, key=score)

