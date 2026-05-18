from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from extractor.http_security import assert_public_url, sanitize_error


LOGGER = logging.getLogger(__name__)
SendLimited = Callable[..., Awaitable[httpx.Response]]


async def maybe_fetch_via_ajax(
    client: httpx.AsyncClient,
    requested_url: str,
    base_response: httpx.Response,
    context: dict[str, Any],
    *,
    max_bytes: int,
    send_limited: SendLimited,
) -> httpx.Response | None:
    if "text/html" not in (base_response.headers.get("content-type", "").lower()):
        return None

    post_data = sen_ajax_post_data(requested_url, context)
    if not post_data:
        return None

    headers = {"Referer": _referer_from_context(context) or requested_url}
    request = client.build_request("POST", _post_endpoint_without_query(requested_url), data=post_data, headers=headers)
    try:
        response = await send_limited(client, request, max_bytes=max_bytes)
        response.raise_for_status()
        assert_public_url(str(response.url))
        response.headers["x-naranhi-fetch-variant"] = "sen_ajax_post"
        return response
    except Exception as exc:  # noqa: BLE001 - enrichment is best-effort.
        LOGGER.warning("sen ajax detail fetch failed: %s", sanitize_error(exc))
        return None


def sen_ajax_post_data(url: str, context: dict[str, Any]) -> dict[str, str] | None:
    parsed = urlparse(url)
    if "selectBoardDetailAjax.do" not in parsed.path:
        return None

    params = parse_qs(parsed.query)
    ntt_id = _first(params.get("nttId")) or _context_value(context, "post_id") or _context_value(context, "source_post_id")
    board_key = _context_value(context, "board_key")
    bbs_id = _context_value(context, "bbsId") or _value_from_board_key(board_key, "bbsId")
    menu_no = _context_value(context, "menuNo") or _value_from_board_key(board_key, "menuNo") or _menu_no_from_url(
        _context_value(context, "board_url") or ""
    )

    if not ntt_id or not bbs_id:
        return None

    data = {"nttId": ntt_id, "bbsId": bbs_id}
    if menu_no:
        data["menuNo"] = menu_no
    return data


def _post_endpoint_without_query(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def _context_value(context: dict[str, Any], key: str) -> str:
    for source in (
        context,
        _dict_value(context, "post"),
        _dict_value(context, "crawl_result"),
        _dict_value(_dict_value(context, "crawl_result"), "post"),
    ):
        value = source.get(key) if isinstance(source, dict) else None
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _dict_value(value: Any, key: str) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get(key), dict):
        return value[key]
    return {}


def _value_from_board_key(board_key: str, key: str) -> str:
    for part in board_key.split("|"):
        name, _, value = part.partition("=")
        if name == key and value:
            return value
    return ""


def _menu_no_from_url(url: str) -> str:
    match = re.search(r"/([0-9]{4,})/subMenu\.do", url)
    return match.group(1) if match else ""


def _referer_from_context(context: dict[str, Any]) -> str:
    return _context_value(context, "board_url") or _context_value(context, "homepage_url")


def _first(values: list[str] | None) -> str:
    return values[0].strip() if values and values[0].strip() else ""
