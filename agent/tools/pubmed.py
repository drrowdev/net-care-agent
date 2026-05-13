"""PubMed E-utilities client (no API key required for basic use)."""

from __future__ import annotations

import requests


def search_pubmed(query: str, max_results: int = 6) -> dict:
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        sr = requests.get(
            f"{base}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance",
            },
            timeout=12,
        )
        sr.raise_for_status()
        ids = sr.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return {"results": [], "query": query, "note": "No results found"}

        fr = requests.get(
            f"{base}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=12,
        )
        fr.raise_for_status()
        raw = fr.json().get("result", {})

        articles = []
        for pmid in ids:
            if pmid not in raw:
                continue
            a = raw[pmid]
            authors = [au.get("name", "") for au in a.get("authors", [])[:3]]
            articles.append(
                {
                    "pmid": pmid,
                    "title": a.get("title", ""),
                    "authors": ", ".join(authors)
                    + (" et al." if len(a.get("authors", [])) > 3 else ""),
                    "journal": a.get("source", ""),
                    "date": a.get("pubdate", ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                }
            )
        return {"results": articles, "query": query, "count": len(articles)}

    except requests.RequestException as e:
        return {"error": str(e), "results": [], "query": query}
