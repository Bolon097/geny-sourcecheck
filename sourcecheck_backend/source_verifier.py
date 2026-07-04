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

URL_RE = re.compile(r"https?://[^\s<>'\"`，。；、（）()\[\]{}]+", re.IGNORECASE)
DOI_RE = re.compile(
    r"(?:doi\s*:\s*|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/[-._;()/:A-Z0-9]+)",
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


def clean_token(value: str) -> str:
    return html.unescape(value).strip(TRIM_CHARS)


def normalize_url(raw: str, default_scheme: str = "https") -> str:
    cleaned = clean_token(raw)
    if not cleaned:
        return ""
    if not re.match(r"^https?://", cleaned, re.IGNORECASE):
        cleaned = f"{default_scheme}://{cleaned}"
    parsed = urlparse(cleaned)
    if not parsed.netloc:
        return cleaned
    scheme = parsed.scheme.lower() if parsed.scheme.lower() in ("http", "https") else default_scheme
    netloc = parsed.netloc.lower()
    return urlunparse((scheme, netloc, parsed.path, "", parsed.query, parsed.fragment))


def _url_dedupe_key(source: str) -> str:
    candidate = source if re.match(r"^https?://", source, re.IGNORECASE) else f"https://{source}"
    parsed = urlparse(candidate)
    if not parsed.netloc:
        return source.lower().rstrip("/")
    netloc = parsed.netloc.lower()
    path = (parsed.path or "").rstrip("/")
    return f"{netloc}{path}?{parsed.query}#{parsed.fragment}".rstrip("?#")


def _is_https_url(source: str) -> bool:
    return source.lower().startswith("https://")


def normalize_doi(raw: str) -> str:
    match = DOI_RE.search(raw)
    if not match:
        return clean_token(raw)
    doi = clean_token(match.group(1)).rstrip(".")
    return f"https://doi.org/{doi}"


def source_words_present(text: str) -> bool:
    lowered = text.lower()
    return any(word.lower() in lowered for word in SOURCE_WORDS)


def _dedupe_key(source_type: str, source: str) -> str:
    if source_type in ("url", "bare_domain"):
        return f"url:{_url_dedupe_key(source)}"
    return f"{source_type}:{source.lower().rstrip('/')}"


def extract_sources(text: str) -> List[Dict[str, Any]]:
    sources: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    url_spans = []

    def add_source(raw: str, source: str, source_type: str) -> None:
        source = normalize_url(source) if source_type in ("url", "bare_domain") else clean_token(source)
        if not source:
            return
        key = _dedupe_key(source_type, source)
        if key in seen:
            existing = sources[seen[key]]
            if _is_https_url(source) and not _is_https_url(str(existing["source"])):
                existing.update({"raw": raw, "source": source, "source_type": source_type})
            return
        seen[key] = len(sources)
        sources.append(
            {
                "raw": raw,
                "source": source,
                "source_type": source_type,
                "level2_status": "not_checked",
                "http_status": None,
                "attempt_url": None,
                "final_url": None,
                "error": None,
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
    source_type = source["source_type"]
    source_value = source["source"]

    if source_type in ("url", "doi"):
        result = _request_once(source_value)
    elif source_type == "bare_domain":
        if source_value.lower().startswith("https://"):
            attempts = [source_value, f"http://{source_value[8:]}"]
        elif source_value.lower().startswith("http://"):
            attempts = [source_value, f"https://{source_value[7:]}"]
        else:
            attempts = [f"https://{source_value}", f"http://{source_value}"]
        result = _request_once(attempts[0])
        if result["level2_status"] not in ("accessible", "restricted_but_exists"):
            result = _request_once(attempts[1])
    else:
        result = {
            "level2_status": "not_checkable_text_only_source",
            "http_status": None,
            "attempt_url": None,
            "final_url": None,
            "error": None,
        }

    checked = dict(source)
    checked.update(result)
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
        if source["level2_status"] not in ("accessible", "restricted_but_exists", "not_checkable_text_only_source")
    )
    url_count = sum(1 for source in sources if source["source_type"] in ("url", "bare_domain"))
    doi_count = sum(1 for source in sources if source["source_type"] == "doi")
    text_only = has_words and not sources

    return {
        "item_id": item_id,
        "level1_status": "passed" if sources or has_words else "failed",
        "has_source_words": has_words,
        "source_count": len(sources),
        "url_count": url_count,
        "doi_count": doi_count,
        "text_only_source_reference": text_only,
        "accessible_count": accessible_count,
        "failed_count": failed_count,
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
