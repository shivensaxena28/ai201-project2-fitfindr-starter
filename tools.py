"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Filter by price
    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    # Filter by size — case-insensitive substring match
    if size is not None:
        size_lower = size.lower()
        listings = [l for l in listings if size_lower in l["size"].lower()]

    # Score by keyword overlap with description
    keywords = set(description.lower().split())

    def _score(listing):
        text = " ".join([
            listing["title"],
            listing.get("description", ""),
            listing.get("category", ""),
            " ".join(listing.get("style_tags", [])),
            " ".join(listing.get("colors", [])),
            listing.get("brand") or "",
        ]).lower()
        return sum(1 for kw in keywords if kw in text)

    scored = [(listing, _score(listing)) for listing in listings]
    # Drop zero-score listings
    scored = [(l, s) for l, s in scored if s > 0]
    # Sort best match first
    scored.sort(key=lambda x: x[1], reverse=True)
    return [l for l, _ in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offers general styling advice for the item.
    """
    try:
        client = _get_groq_client()
    except ValueError as e:
        return f"Could not generate outfit suggestion: {e}"

    item_desc = (
        f"{new_item['title']} — {new_item.get('description', '')} "
        f"(Colors: {', '.join(new_item.get('colors', []))}; "
        f"Style: {', '.join(new_item.get('style_tags', []))})"
    )

    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = (
            f"A user just found this secondhand item: {item_desc}\n\n"
            "They don't have a wardrobe on file yet. Give them 1–2 specific outfit "
            "suggestions explaining what types of pieces to pair it with, the overall "
            "vibe, and any simple styling tips (e.g., tucking, layering). "
            "Be specific and practical — don't just say 'casual' or 'streetwear'."
        )
    else:
        wardrobe_text = "\n".join(
            f"- {item['name']} ({item['category']}, colors: {', '.join(item['colors'])}"
            + (f", notes: {item['notes']}" if item.get("notes") else "") + ")"
            for item in wardrobe_items
        )
        prompt = (
            f"A user just found this secondhand item: {item_desc}\n\n"
            f"Here is their current wardrobe:\n{wardrobe_text}\n\n"
            "Suggest 1–2 complete outfits using the new item combined with specific "
            "named pieces from their wardrobe above. For each outfit: name the exact "
            "pieces, describe how to style them (silhouette, tuck/untuck, layering), "
            "and explain the vibe in concrete terms."
        )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=512,
        )
        result = response.choices[0].message.content.strip()
        return result if result else "No outfit suggestion generated — try a different item."
    except Exception as e:
        return (
            f"Could not generate outfit suggestion (LLM error: {e}). "
            "Try searching for a different item or check your API key."
        )


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string.
    """
    if not outfit or not outfit.strip():
        return (
            "Cannot generate a fit card without an outfit suggestion. "
            "Please try the search again."
        )

    title = new_item.get("title", "this thrifted piece")
    price = new_item.get("price", "?")
    platform = new_item.get("platform", "a thrift platform")

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok caption for this thrifted outfit.\n\n"
        f"Item found: {title} — ${price} on {platform}\n"
        f"Outfit: {outfit}\n\n"
        "Rules:\n"
        "- Write in casual first-person (like a real OOTD post, not a product description)\n"
        "- Mention the item name, price, and platform once each, naturally\n"
        "- Capture the outfit vibe in specific, vivid terms\n"
        "- Keep it under 4 sentences\n"
        "- Sound authentic and human — avoid corporate or generic phrasing\n"
        "Return only the caption text, nothing else."
    )

    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=1.2,
            max_tokens=200,
        )
        result = response.choices[0].message.content.strip()
        return result if result else (
            f"Fit card generation returned empty — but you found: "
            f"{title} for ${price} on {platform}."
        )
    except Exception as e:
        return (
            f"Fit card generation failed — but here's what you found: "
            f"{title} for ${price} on {platform}. (Error: {e})"
        )
