from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup
import httpx

from app.crawler.http_client import make_async_client_for_url, with_retries


@dataclass(frozen=True)
class FetchedPage:
    url: str
    final_url: str
    status_code: int
    html: str
    title: str


class HomepageClient:
    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    async def fetch(self, url: str, follow_js_redirect: bool = True) -> FetchedPage:
        first_error: Exception | None = None
        last_error: Exception | None = None
        for candidate_url in url_variants(url):
            async with make_async_client_for_url(url=candidate_url, timeout=self.timeout) as client:
                try:
                    return await with_retries(
                        lambda candidate_url=candidate_url: _fetch_with_client(
                            client,
                            candidate_url,
                            follow_js_redirect=follow_js_redirect,
                        ),
                        retries=2,
                        base_delay=0.75,
                    )
                except Exception as exc:  # noqa: BLE001 - try homepage URL variants.
                    if first_error is None:
                        first_error = exc
                    last_error = exc

        if first_error:
            raise first_error
        if last_error:
            raise last_error
        raise RuntimeError(f"fetch failed: {url}")


async def _fetch_with_client(
    client: httpx.AsyncClient,
    url: str,
    *,
    follow_js_redirect: bool,
    max_js_redirects: int = 5,
) -> FetchedPage:
    current_url = url
    seen_urls: set[str] = set()
    response: httpx.Response | None = None

    for _ in range(max_js_redirects + 1):
        response = await client.get(current_url)
        response.raise_for_status()
        html = response.text

        if not follow_js_redirect:
            break

        js_redirect_url = extract_js_redirect_url(str(response.url), html)
        if not js_redirect_url or js_redirect_url in seen_urls:
            break

        seen_urls.add(js_redirect_url)
        current_url = js_redirect_url

    if response is None:
        raise RuntimeError(f"fetch failed: {url}")

    return FetchedPage(
        url=url,
        final_url=str(response.url),
        status_code=response.status_code,
        html=response.text,
        title="",
    )


def url_variants(url: str) -> list[str]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return [url]

    schemes = [parsed.scheme]
    if parsed.scheme == "https":
        schemes.append("http")
    elif parsed.scheme == "http":
        schemes.append("https")

    netlocs = [parsed.netloc]
    if parsed.netloc.startswith("www."):
        netlocs.append(parsed.netloc[4:])
    else:
        netlocs.append(f"www.{parsed.netloc}")

    variants: list[str] = []
    for scheme in schemes:
        for netloc in netlocs:
            candidates = [
                urlunparse(
                    (
                        scheme,
                        netloc,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    )
                )
            ]
            if parsed.path and parsed.path != "/":
                candidates.append(urlunparse((scheme, netloc, "/", "", "", "")))
            for candidate in candidates:
                if candidate not in variants:
                    variants.append(candidate)

    return variants


def extract_js_redirect_url(base_url: str, html: str) -> str | None:
    if not _looks_like_redirect_page(html):
        return None

    patterns = (
        r"""(?:window|document|top|parent)?\.?location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""",
        r"""(?:window|document|top|parent)?\.?location\.replace\(\s*['"]([^'"]+)['"]\s*\)""",
        r"""(?:window|document|top|parent)?\.?location\.assign\(\s*['"]([^'"]+)['"]\s*\)""",
    )

    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            return urljoin(base_url, match.group(1).strip())

    soup = BeautifulSoup(html, "html.parser")
    meta = soup.find(
        "meta",
        attrs={
            "http-equiv": lambda value: isinstance(value, str)
            and value.lower() == "refresh"
        },
    )
    if meta:
        content = meta.get("content") or ""
        meta_match = re.search(r"url\s*=\s*([^;]+)", content, re.IGNORECASE)
        if meta_match:
            return urljoin(base_url, meta_match.group(1).strip(" '\""))

    return None


def _looks_like_redirect_page(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = " ".join(soup.get_text(" ", strip=True).split())
    anchors = soup.find_all("a")

    if len(visible_text) <= 80 and len(anchors) == 0:
        return True
    if soup.title and soup.title.string and soup.title.string.strip().lower() in {"cms", "welcome homepage"} and len(anchors) == 0:
        return True
    return False

