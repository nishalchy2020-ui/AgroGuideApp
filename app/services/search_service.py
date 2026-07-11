import logging
import os
import time

import requests
from flask import current_app
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_logger = logging.getLogger("agroguide")
_http = requests.Session()
_retry = Retry(
    total=2,
    backoff_factor=0.5,
    status_forcelist=(429, 502, 503, 504),
    allowed_methods=frozenset(["GET", "POST"]),
)
_http.mount("http://", HTTPAdapter(max_retries=_retry))
_http.mount("https://", HTTPAdapter(max_retries=_retry))
_CACHE = {}
_CACHE_TTL_SECONDS = 1800


class SearchUnavailable(RuntimeError):
    pass


def _settings():
    try:
        provider = (current_app.config.get("SEARCH_PROVIDER") or "tavily").strip().lower()
        api_key = (current_app.config.get("SEARCH_API_KEY") or "").strip()
        google_api_key = (current_app.config.get("GOOGLE_SEARCH_API_KEY") or "").strip()
        google_cse_id = (current_app.config.get("GOOGLE_CSE_ID") or "").strip()
    except RuntimeError:
        provider = (os.getenv("SEARCH_PROVIDER") or "tavily").strip().lower()
        api_key = (os.getenv("SEARCH_API_KEY") or "").strip()
        google_api_key = (os.getenv("GOOGLE_SEARCH_API_KEY") or "").strip()
        google_cse_id = (os.getenv("GOOGLE_CSE_ID") or "").strip()
    return provider, api_key, google_api_key, google_cse_id


def search_web(query, max_results=5):
    provider, api_key, google_api_key, _google_cse_id = _settings()

    cache_key = (provider, query.strip().lower(), int(max_results))
    cached = _CACHE.get(cache_key)
    if cached and cached["expires_at"] > time.time():
        _logger.info("Using cached search result for provider=%s query=%s", provider, query)
        return cached["data"]

    if provider == "tavily":
        if not api_key:
            raise SearchUnavailable("SEARCH_API_KEY is not configured.")
        data = _search_tavily(query, api_key, max_results)
    elif provider == "serpapi":
        if not api_key:
            raise SearchUnavailable("SEARCH_API_KEY is not configured.")
        data = _search_serpapi(query, api_key, max_results)
    elif provider == "brave":
        if not api_key:
            raise SearchUnavailable("SEARCH_API_KEY is not configured.")
        data = _search_brave(query, api_key, max_results)
    elif provider in {"google", "google_custom_search"}:
        effective_key = google_api_key or api_key
        if not effective_key:
            raise SearchUnavailable("GOOGLE_SEARCH_API_KEY is not configured.")
        data = _search_google_custom(query, effective_key, max_results)
    else:
        raise SearchUnavailable(f"Unsupported SEARCH_PROVIDER={provider!r}.")

    _CACHE[cache_key] = {"expires_at": time.time() + _CACHE_TTL_SECONDS, "data": data}
    return data


def search_all_sources(query, max_results_per_provider=4):
    provider, api_key, google_api_key, google_cse_id = _settings()
    results = []
    errors = []

    if api_key:
        for name, fn in (("tavily", _search_tavily),):
            try:
                data = _cached_provider_search(
                    name,
                    query,
                    lambda: fn(query, api_key, max_results_per_provider),
                    max_results_per_provider,
                )
                results.extend(_flatten_search_data(data))
            except Exception as exc:
                _logger.warning("%s search failed: %s", name, exc)
                errors.append(f"{name}: {exc}")

    if google_cse_id and google_api_key:
        try:
            data = _cached_provider_search(
                "google",
                query,
                lambda: _search_google_custom(query, google_api_key, max_results_per_provider),
                max_results_per_provider,
            )
            results.extend(_flatten_search_data(data))
        except Exception as exc:
            _logger.warning("Google CSE search failed: %s", exc)
            errors.append(f"google: {exc}")
    elif provider in {"google", "google_custom_search"} and not google_api_key:
        errors.append("google: GOOGLE_SEARCH_API_KEY is not configured")

    if not results:
        raise SearchUnavailable("; ".join(errors) or "No search providers configured.")
    return results


def _cached_provider_search(provider, query, loader, max_results):
    cache_key = (provider, query.strip().lower(), int(max_results))
    cached = _CACHE.get(cache_key)
    if cached and cached["expires_at"] > time.time():
        _logger.info("Using cached search result for provider=%s query=%s", provider, query)
        return cached["data"]
    data = loader()
    _CACHE[cache_key] = {"expires_at": time.time() + _CACHE_TTL_SECONDS, "data": data}
    return data


def _flatten_search_data(data):
    provider = data.get("provider", "search")
    items = []
    answer = (data.get("answer") or "").strip()
    if answer:
        items.append(
            {
                "title": f"{provider.title()} answer",
                "snippet": answer,
                "url": None,
                "source": provider,
            }
        )
    for item in data.get("results", [])[:5]:
        snippet = (item.get("snippet") or "").strip()
        if not snippet:
            continue
        items.append(
            {
                "title": item.get("title") or "Search result",
                "snippet": snippet,
                "url": item.get("url"),
                "source": provider,
            }
        )
    return items


def _search_tavily(query, api_key, max_results):
    response = _http.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": True,
            "max_results": max_results,
        },
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    results = [
        {
            "title": item.get("title") or item.get("url") or "Source",
            "url": item.get("url"),
            "snippet": item.get("content") or "",
        }
        for item in data.get("results", [])
    ]
    answer = data.get("answer") or ""
    return {"answer": answer, "results": results, "provider": "tavily"}


def _search_serpapi(query, api_key, max_results):
    response = _http.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "api_key": api_key, "num": max_results},
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    results = [
        {
            "title": item.get("title") or item.get("link") or "Source",
            "url": item.get("link"),
            "snippet": item.get("snippet") or "",
        }
        for item in data.get("organic_results", [])[:max_results]
    ]
    return {"answer": data.get("answer_box", {}).get("answer", ""), "results": results, "provider": "serpapi"}


def _search_brave(query, api_key, max_results):
    response = _http.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max_results},
        headers={"Accept": "application/json", "X-Subscription-Token": api_key},
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    web = data.get("web", {}).get("results", [])
    results = [
        {
            "title": item.get("title") or item.get("url") or "Source",
            "url": item.get("url"),
            "snippet": item.get("description") or "",
        }
        for item in web[:max_results]
    ]
    return {"answer": "", "results": results, "provider": "brave"}


def _search_google_custom(query, api_key, max_results):
    cx = (current_app.config.get("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CSE_ID") or "").strip()
    if not cx:
        raise SearchUnavailable("GOOGLE_CSE_ID is required for Google Custom Search.")
    response = _http.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": api_key, "cx": cx, "q": query, "num": max_results},
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    results = [
        {
            "title": item.get("title") or item.get("link") or "Source",
            "url": item.get("link"),
            "snippet": item.get("snippet") or "",
        }
        for item in data.get("items", [])[:max_results]
    ]
    return {"answer": "", "results": results, "provider": "google"}


def summarize_search_results(question, search_data):
    results = search_data.get("results", [])
    answer = (search_data.get("answer") or "").strip()
    snippets = [item.get("snippet", "").strip() for item in results if item.get("snippet")]
    if not answer and len(snippets) < 1:
        raise SearchUnavailable("Search returned no useful farming result.")

    if answer:
        direct = answer
    elif snippets:
        direct = " ".join(snippets[:2])
    else:
        raise SearchUnavailable("Search returned no usable results.")

    direct = " ".join(direct.split())
    if len(direct) > 520:
        direct = direct[:520].rsplit(" ", 1)[0] + "."

    source_lines = []
    for item in results[:3]:
        title = item.get("title") or "Source"
        url = item.get("url")
        source_lines.append(f"- {title}: {url}" if url else f"- {title}")

    recommendation = _practical_recommendation(question, direct)
    return (
        "Direct answer: "
        + direct
        + "\n\nPractical recommendation: "
        + recommendation
        + "\n\nSources:\n"
        + "\n".join(source_lines or ["- Online search result"])
        + "\n\nRegional note: Farming recommendations can vary by crop variety, climate, soil test, local regulations, and pesticide labels."
    )


def _practical_recommendation(question, direct):
    text = f"{question} {direct}".lower()
    if any(word in text for word in ("disease", "blight", "rust", "spot", "mildew")):
        return "Inspect several plants, remove badly infected leaves, avoid overhead irrigation, and confirm diagnosis with a leaf scan or local extension expert before spraying."
    if any(word in text for word in ("fertilizer", "npk", "nitrogen", "phosphorus", "potassium")):
        return "Use a soil test before applying fertilizer, split applications where possible, and avoid excess nitrogen during flowering or fruiting."
    if any(word in text for word in ("irrigation", "water", "rain", "drought")):
        return "Check soil moisture near the root zone, prefer drip irrigation, and adjust scheduling after rainfall or during heat waves."
    if any(word in text for word in ("pest", "aphid", "mite", "worm", "insect")):
        return "Scout weekly, identify the pest, start with cultural or biological controls, and follow label directions for any pesticide."
    return "Compare the online guidance with your field conditions, soil test, crop stage, and local extension advice before acting."


def safe_search_answer(question):
    try:
        data = search_web(f"{question} agriculture farming crop advice")
        return summarize_search_results(question, data), data.get("results", [])
    except SearchUnavailable:
        raise
    except Exception as exc:
        _logger.exception("Internet search failed.")
        raise SearchUnavailable(str(exc)) from exc
