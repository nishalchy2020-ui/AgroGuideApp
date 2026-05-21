import logging
import os

import requests
from flask import current_app

_logger = logging.getLogger("agroguide")


class SearchUnavailable(RuntimeError):
    pass


def _settings():
    try:
        provider = (current_app.config.get("SEARCH_PROVIDER") or "tavily").strip().lower()
        api_key = (current_app.config.get("SEARCH_API_KEY") or "").strip()
    except RuntimeError:
        provider = (os.getenv("SEARCH_PROVIDER") or "tavily").strip().lower()
        api_key = (os.getenv("SEARCH_API_KEY") or "").strip()
    return provider, api_key


def search_web(query, max_results=5):
    provider, api_key = _settings()
    if not api_key:
        raise SearchUnavailable("SEARCH_API_KEY is not configured.")

    if provider == "tavily":
        return _search_tavily(query, api_key, max_results)
    if provider == "serpapi":
        return _search_serpapi(query, api_key, max_results)
    if provider == "brave":
        return _search_brave(query, api_key, max_results)
    if provider in {"google", "google_custom_search"}:
        return _search_google_custom(query, api_key, max_results)

    raise SearchUnavailable(f"Unsupported SEARCH_PROVIDER={provider!r}.")


def _search_tavily(query, api_key, max_results):
    response = requests.post(
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
    response = requests.get(
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
    response = requests.get(
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
    cx = (current_app.config.get("GOOGLE_CSE_ID") or "").strip()
    if not cx:
        raise SearchUnavailable("GOOGLE_CSE_ID is required for Google Custom Search.")
    response = requests.get(
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
