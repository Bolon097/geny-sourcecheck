import html
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse


SOURCE_WORDS = [
    "source",
    "sources",
    "reference",
    "references",
    "according to",
    "data from",
    "cited from",
    "来源",
    "参考",
    "数据来源",
    "链接",
    "出处",
    "引用",
]

KNOWN_NAMED_SOURCES = [
    "杭州市政府网",
    "杭州市人民政府门户网站",
    "杭州数据开放平台",
    "浙江省公共数据开放平台",
    "杭州市城乡建设委员会",
    "杭州市发展和改革委员会",
    "杭州市交通运输局",
    "杭州市统计局",
    "Hangzhou municipal government platform",
    "Amap",
    "Amap charging platform",
    "Baidu Maps",
    "WeChat mini-program",
]

URL_RE = re.compile(r"https?://[^\s<>'\"`，。；、（）()\[\]{}]+", re.IGNORECASE)
HTTPS_URL_RE = re.compile(r"https://[^\s\"'<>]+", re.IGNORECASE)
DOI_RE = re.compile(
    r"(?:doi\s*:\s*)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
    re.IGNORECASE,
)
COMMON_TLDS = (
    "com",
    "org",
    "net",
    "edu",
    "gov",
    "cn",
    "ac",
    "uk",
    "us",
    "info",
    "io",
    "co",
)
DOMAIN_RE = re.compile(
    r"(?<![@\w.-])"
    r"("
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:" + "|".join(COMMON_TLDS) + r")"
    r"(?::\d{2,5})?"
    r"(?:(?:/[^\s<>'\"`，。；、（）()\[\]{}]*)|(?:\?[^\s<>'\"`，。；、（）()\[\]{}]*)|(?:#[^\s<>'\"`，。；、（）()\[\]{}]*))?"
    r")",
    re.IGNORECASE,
)

TRIM_CHARS = " \t\r\n<>[](){}（）【】「」『』“”‘’\"'`.,;:，。；：、！!？?）]】"
REQUEST_TIMEOUT_SECONDS = 10
USER_AGENT = "SourceCheck/0.1 local verification prototype"
NOT_CHECKED_REASON = (
    "Level 2 only checks explicit HTTP/HTTPS URLs and DOI references in this prototype."
)


def clean_token(value: str) -> str:
    return html.unescape(value).strip(TRIM_CHARS)


def extract_https_urls(text: str) -> List[str]:
    """Return only URLs that explicitly start with https://."""
    return [clean_token(match.group(0)) for match in HTTPS_URL_RE.finditer(text)]


def normalize_url(raw: str) -> str:
    cleaned = clean_token(raw)
    if not cleaned:
        return ""
    parsed = urlparse(cleaned)
    if not parsed.netloc:
        return cleaned
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    return urlunparse((scheme, netloc, parsed.path, "", parsed.query, parsed.fragment))


def _url_dedupe_key(source: str) -> str:
    parsed = urlparse(source)
    if not parsed.netloc:
        return source.lower().rstrip("/")
    netloc = parsed.netloc.lower()
    path = (parsed.path or "").rstrip("/")
    return f"{netloc}{path}?{parsed.query}#{parsed.fragment}".rstrip("?#")


def _is_https_url(source: str) -> bool:
    return source.lower().startswith("https://")


def _is_explicit_http_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def normalize_doi(raw: str) -> str:
    match = DOI_RE.search(raw)
    if not match:
        return clean_token(raw)
    doi = clean_token(match.group(1)).rstrip(".")
    return f"https://doi.org/{doi}"


def source_words_present(text: str) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in SOURCE_WORDS)


def _is_machine_checkable(source_type: str, source: str) -> bool:
    if source_type == "url":
        return _is_explicit_http_url(source)
    if source_type == "doi":
        return _is_https_url(source)
    return False


def _dedupe_key(source_type: str, source: str) -> str:
    if source_type == "url":
        return f"url:{_url_dedupe_key(source)}"
    if source_type == "doi":
        return f"doi:{source.lower().rstrip('/')}"
    return f"{source_type}:{source.lower().rstrip('/')}"


def extract_sources(text: str) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    url_spans = []

    def add_source(raw: str, source: str, source_type: str) -> None:
        source = normalize_url(source) if source_type in ("url", "doi") else clean_token(source)
        if not source:
            return
        key = _dedupe_key(source_type, source)
        if key in seen:
            existing = sources[seen[key]]
            if source_type == "doi" and existing["source_type"] != "doi":
                existing.update({"raw": raw, "source": source, "source_type": source_type})
                existing["is_machine_checkable"] = True
                existing["reason"] = ""
            elif source_type == "url" and _is_https_url(source) and not _is_https_url(str(existing["source"])):
                existing.update({"raw": raw, "source": source, "source_type": source_type})
                existing["is_machine_checkable"] = True
                existing["reason"] = ""
            elif _is_machine_checkable(source_type, source) and not existing.get("is_machine_checkable"):
                existing.update({"raw": raw, "source": source, "source_type": source_type})
                existing["is_machine_checkable"] = True
                existing["reason"] = ""
            return
        is_machine_checkable = _is_machine_checkable(source_type, source)
        seen[key] = len(sources)
        sources.append(
            {
                "raw": raw,
                "source": source,
                "source_type": source_type,
                "is_machine_checkable": is_machine_checkable,
                "level1_status": "source_signal_detected",
                "level2_status": "not_checked",
                "http_status": None,
                "attempt_url": None,
                "final_url": None,
                "error": None,
                "reason": "" if is_machine_checkable else NOT_CHECKED_REASON,
            }
        )

    for match in URL_RE.finditer(text):
        url_spans.append(match.span())
        raw = clean_token(match.group(0))
        if "doi.org/" in raw.lower():
            add_source(match.group(0), normalize_doi(raw), "doi")
        else:
            add_source(match.group(0), raw, "url")

    for match in DOI_RE.finditer(text):
        raw = match.group(0)
        add_source(raw, normalize_doi(raw), "doi")

    for match in DOMAIN_RE.finditer(text):
        if any(start <= match.start() and match.end() <= end for start, end in url_spans):
            continue
        raw = match.group(1)
        cleaned = clean_token(raw)
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered.startswith(("http://", "https://")):
            continue
        if "doi.org/" in lowered:
            continue
        add_source(raw, cleaned, "bare_domain")

    for name in KNOWN_NAMED_SOURCES:
        if name in text:
            add_source(name, name, "named_source")

    if source_words_present(text) and not sources:
        add_source("source-related wording", "source-related wording", "source_wording")

    return sources


def classify_status(status_code: Optional[int], error_kind: Optional[str] = None) -> str:
    if error_kind:
        return error_kind
    if status_code is None:
        return "request_error"
    if 200 <= status_code < 400:
        return "accessible"
    if status_code in (401, 403):
        return "restricted_but_exists"
    if status_code in (404, 410):
        return "broken"
    if 500 <= status_code < 600:
        return "server_error"
    return "request_error"


def _request_once(url: str) -> Dict[str, Any]:
    import requests

    headers = {"User-Agent": USER_AGENT}
    response = None
    try:
        response = requests.head(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
            headers=headers,
        )
        if response.status_code in (403, 405, 406) or 500 <= response.status_code < 600:
            response.close()
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=True,
                headers=headers,
                stream=True,
            )
        status = response.status_code
        return {
            "level2_status": classify_status(status),
            "http_status": status,
            "attempt_url": url,
            "final_url": response.url,
            "error": None,
        }
    except requests.exceptions.Timeout as exc:
        return _error_result(url, "timeout", exc)
    except requests.exceptions.SSLError as exc:
        return _error_result(url, "ssl_error", exc)
    except requests.exceptions.RequestException as exc:
        return _error_result(url, "request_error", exc)
    finally:
        if response is not None:
            response.close()


def _error_result(url: str, status: str, exc: Exception) -> Dict[str, Any]:
    return {
        "level2_status": status,
        "http_status": None,
        "attempt_url": url,
        "final_url": None,
        "error": str(exc),
    }


def check_source(source: Dict[str, Any]) -> Dict[str, Any]:
    checked = dict(source)
    source_type = checked.get("source_type")
    source_value = checked.get("source", "")

    if source_type == "url":
        result = _request_once(source_value)
        checked.update(result)
        checked.setdefault("reason", "")
        return checked

    if source_type == "doi":
        result = _request_once(source_value)
        checked.update(result)
        checked.setdefault("reason", "")
        return checked

    if not checked.get("is_machine_checkable"):
        checked.update(
            {
                "level2_status": "not_machine_checked_level1_signal",
                "http_status": None,
                "attempt_url": None,
                "final_url": None,
                "error": None,
                "reason": checked.get("reason") or NOT_CHECKED_REASON,
            }
        )
        return checked

    return checked


def verify_response(response: str, item_id: Optional[Any] = None, perform_level2: bool = True) -> Dict[str, Any]:
    text = response or ""
    has_words = source_words_present(text)
    sources = extract_sources(text)

    if perform_level2:
        sources = [check_source(source) for source in sources]

    accessible_count = sum(1 for source in sources if source["level2_status"] in ("accessible", "restricted_but_exists"))
    failed_count = sum(
        1
        for source in sources
        if source.get("is_machine_checkable")
        and source["level2_status"] not in ("accessible", "restricted_but_exists", "not_checked")
    )
    machine_checkable_count = sum(1 for source in sources if source.get("is_machine_checkable"))
    url_count = sum(1 for source in sources if source["source_type"] == "url")
    doi_count = sum(1 for source in sources if source["source_type"] == "doi")
    bare_domain_count = sum(1 for source in sources if source["source_type"] == "bare_domain")
    not_machine_checked_count = sum(1 for source in sources if not source.get("is_machine_checkable"))
    text_only = has_words and not any(source["source_type"] != "source_wording" for source in sources)

    return {
        "item_id": item_id,
        "level1_status": "passed" if sources or has_words else "failed",
        "has_source_words": has_words,
        "source_count": len(sources),
        "machine_checkable_count": machine_checkable_count,
        "url_count": url_count,
        "doi_count": doi_count,
        "bare_domain_count": bare_domain_count,
        "text_only_source_reference": text_only,
        "accessible_count": accessible_count,
        "failed_count": failed_count,
        "not_machine_checked_count": not_machine_checked_count,
        "not_checked_count": not_machine_checked_count,
        "level3_status": "not_implemented",
        "level3_note": (
            "Level 3 claim-support verification is not implemented in this prototype. "
            "It would require checking whether the source actually supports the specific claims, "
            "numbers, and meanings in the AI response."
        ),
        "sources": sources,
    }


def verify_batch(items: List[Dict[str, Any]], perform_level2: bool = True) -> Dict[str, Any]:
    answer_level_results = []
    source_level_results = []
    for index, item in enumerate(items, start=1):
        item_id = item.get("item_id", index)
        result = verify_response(item.get("response", ""), item_id=item_id, perform_level2=perform_level2)
        answer_level_results.append({key: value for key, value in result.items() if key != "sources"})
        for source in result["sources"]:
            row = {"item_id": item_id}
            row.update(source)
            source_level_results.append(row)
    return {
        "answer_level_results": answer_level_results,
        "source_level_results": source_level_results,
    }
