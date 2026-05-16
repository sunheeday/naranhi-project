from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


NEIS_BASE_URL = "https://open.neis.go.kr/hub"
ALLOWED_LEVELS = {"초등학교", "중학교"}


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
                    level = str(row.get("SCHUL_KND_SC_NM") or "").strip()
                    if level not in ALLOWED_LEVELS:
                        continue

                    office_code = str(row.get("ATPT_OFCDC_SC_CODE") or "").strip()
                    school_code = str(row.get("SD_SCHUL_CODE") or "").strip()
                    homepage_url = normalize_homepage_url(row.get("HMPG_ADRES"))
                    if not homepage_url:
                        continue

                    school = School(
                        name=str(row.get("SCHUL_NM") or "").strip(),
                        level=level,
                        office_code=office_code,
                        school_code=school_code,
                        address=str(row.get("ORG_RDNMA") or "").strip(),
                        homepage_url=homepage_url,
                    )
                    found[(office_code, school_code)] = school

        return _rank_schools(query, list(found.values()))


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

