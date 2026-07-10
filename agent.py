"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage:
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Use the LLM to extract structured search parameters from a natural language query.

    Returns a dict with keys: description (str), size (str or None), max_price (float or None).
    Falls back to using the full query as description with no filters if LLM call fails.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"description": query, "size": None, "max_price": None}

    prompt = (
        "Extract search parameters from this thrift shopping query. "
        "Return ONLY a JSON object with these exact keys:\n"
        '- "description": the item being searched for (str, required)\n'
        '- "size": size filter if mentioned (str or null)\n'
        '- "max_price": maximum price as a number if mentioned (float or null)\n\n'
        f"Query: {query}\n\n"
        "Return only valid JSON, nothing else. Example:\n"
        '{"description": "vintage graphic tee", "size": "M", "max_price": 30.0}'
    )

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        text = response.choices[0].message.content.strip()
        # Extract JSON from the response (handles cases where model adds extra text)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            parsed = json.loads(match.group())
            return {
                "description": str(parsed.get("description") or query),
                "size": parsed.get("size") or None,
                "max_price": float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
            }
    except Exception:
        pass

    # Fallback: use full query as description
    return {"description": query, "size": None, "max_price": None}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        The session dict. Check session["error"] first — if not None, the
        interaction ended early and outfit_suggestion/fit_card will be None.
    """
    # Step 1: Initialize session
    session = _new_session(query, wardrobe)

    # Step 2: Parse the query into structured parameters
    session["parsed"] = _parse_query(query)
    description = session["parsed"]["description"]
    size = session["parsed"]["size"]
    max_price = session["parsed"]["max_price"]

    # Step 3: Search for listings
    session["search_results"] = search_listings(description, size, max_price)

    # Branch: no results → set error and return early
    if not session["search_results"]:
        parts = [f"'{description}'"]
        if size:
            parts.append(f"in size {size}")
        if max_price is not None:
            parts.append(f"under ${max_price:.2f}")
        session["error"] = (
            f"No listings found for {' '.join(parts)}. "
            "Try broadening your search — remove the size filter, raise the price, "
            "or use different keywords."
        )
        return session

    # Step 4: Select the top result
    session["selected_item"] = session["search_results"][0]

    # Step 5: Suggest outfit combinations
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"], session["wardrobe"]
    )

    # Step 6: Generate the fit card caption
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"], session["selected_item"]
    )

    # Step 7: Return completed session
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}")

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
