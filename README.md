# FitFindr

A multi-tool AI agent that helps users find secondhand pieces and figure out how to style them. Given a natural language query, FitFindr searches mock thrift listings, suggests outfit combinations using the user's wardrobe, and generates a shareable fit card caption.

## Demo Video

[Watch the demo on Loom](https://www.loom.com/share/3a1e2de4f7234abc8655e722cf522064)

## Setup

**macOS / Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows:**
```bash
python -m venv .venv
source .venv/Scripts/activate      # Git Bash
# or: .venv\Scripts\activate       # Command Prompt
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit this):
```
GROQ_API_KEY=your_key_here
```

Get a free Groq key at [console.groq.com](https://console.groq.com) — no credit card required.

**Run the app:**
```bash
python app.py
```
Then open the URL shown in your terminal (usually http://localhost:7860).

**Run tests:**
```bash
pytest tests/
```

---

## Tool Inventory

### Tool 1: `search_listings`

**Function signature:** `search_listings(description: str, size: str | None, max_price: float | None) -> list[dict]`

| Parameter | Type | Description |
|-----------|------|-------------|
| `description` | `str` | Keywords describing the item (e.g., "vintage graphic tee"). Matched against title, description, style_tags, category, colors, and brand. |
| `size` | `str \| None` | Size filter string, or `None` to skip. Case-insensitive substring match — "M" matches "S/M" and "M". |
| `max_price` | `float \| None` | Maximum price (inclusive), or `None` to skip price filtering. |

**Returns:** A `list[dict]` sorted by relevance (best match first). Each dict contains: `id` (str), `title` (str), `description` (str), `category` (str — one of tops/bottoms/outerwear/shoes/accessories), `style_tags` (list[str]), `size` (str), `condition` (str — excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str — depop/thredUp/poshmark). Returns `[]` if nothing matches — never raises an exception.

**Purpose:** Filters and scores the 40-item mock listings dataset against the user's search criteria without calling the LLM.

---

### Tool 2: `suggest_outfit`

**Function signature:** `suggest_outfit(new_item: dict, wardrobe: dict) -> str`

| Parameter | Type | Description |
|-----------|------|-------------|
| `new_item` | `dict` | A listing dict (the top result from `search_listings`). |
| `wardrobe` | `dict` | A wardrobe dict with an `items` key containing a list of wardrobe item dicts, each with: `id`, `name`, `category`, `colors`, `style_tags`, `notes`. May have an empty `items` list. |

**Returns:** A non-empty string with 1–2 outfit suggestions. When the wardrobe has items, suggestions reference specific named pieces by name. When the wardrobe is empty, the string contains general styling advice (types of pieces that pair well, overall vibe, styling tips). Never returns an empty string.

**Purpose:** Calls the Groq LLM (llama-3.3-70b-versatile) to generate human-readable outfit combinations from the item + wardrobe data.

---

### Tool 3: `create_fit_card`

**Function signature:** `create_fit_card(outfit: str, new_item: dict) -> str`

| Parameter | Type | Description |
|-----------|------|-------------|
| `outfit` | `str` | The outfit suggestion string returned by `suggest_outfit()`. Must be non-empty. |
| `new_item` | `dict` | The listing dict for the thrifted item. Used for `title`, `price`, and `platform`. |

**Returns:** A 2–4 sentence string written in casual first-person OOTD tone. Mentions the item name, price, and platform once each. Captures the outfit vibe in specific terms. Uses LLM temperature 1.2 to produce different output each call for different inputs. If `outfit` is empty or whitespace-only, returns an error string without calling the LLM.

**Purpose:** Generates a shareable social media caption summarizing the thrifted find and the outfit context.

---

## Planning Loop

The planning loop in `run_agent()` follows this conditional logic:

1. **Initialize session** — creates a fresh `session` dict with keys for `query`, `parsed`, `search_results`, `selected_item`, `wardrobe`, `outfit_suggestion`, `fit_card`, and `error`.

2. **Parse the query** — calls the LLM with a zero-temperature prompt asking it to extract `description` (str), `size` (str or null), and `max_price` (float or null) from the natural language query. Falls back to using the full query as description with no filters if parsing fails.

3. **Call `search_listings`** — uses the parsed parameters. Stores results in `session["search_results"]`.
   - **Branch: results is empty** → sets `session["error"]` to a specific message naming what was searched and suggesting what to try. **Returns the session immediately.** `suggest_outfit` and `create_fit_card` are NOT called.
   - **Branch: results non-empty** → sets `session["selected_item"] = results[0]` and continues.

4. **Call `suggest_outfit`** — passes `session["selected_item"]` and `session["wardrobe"]`. Stores the result string in `session["outfit_suggestion"]`.

5. **Call `create_fit_card`** — passes `session["outfit_suggestion"]` and `session["selected_item"]`. Stores the result string in `session["fit_card"]`.

6. **Return session** — `session["error"]` is `None` on success.

The loop terminates early **only** when `search_listings` returns no results. LLM errors in steps 4–5 produce degraded-but-informative strings rather than crashing the loop.

---

## State Management

All state lives in a single `session` dict created by `_new_session()` at the start of each `run_agent()` call. Each step reads from and writes to this same dict:

| Key | Type | Set at step | Passed to |
|-----|------|-------------|-----------|
| `query` | str | Initialization | Never modified |
| `parsed` | dict | Step 2 (query parse) | Used for search params |
| `search_results` | list[dict] | Step 3 (`search_listings`) | Source for `selected_item` |
| `selected_item` | dict | Step 3 (top result) | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | dict | Initialization | `suggest_outfit` |
| `outfit_suggestion` | str | Step 4 (`suggest_outfit`) | `create_fit_card` |
| `fit_card` | str | Step 5 (`create_fit_card`) | Displayed to user |
| `error` | str | Step 3 on failure | Displayed to user |

No data is re-requested from the user between steps. The `selected_item` dict set in step 3 is the exact same object passed into `suggest_outfit` in step 4 and `create_fit_card` in step 5.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No results match the query (empty list returned) | Sets `session["error"]` to: "No listings found for '[description]' in size [size] under $[price]. Try broadening your search — remove the size filter, raise the price, or use different keywords." Returns the session immediately; `suggest_outfit` and `create_fit_card` are not called. |
| `suggest_outfit` | Wardrobe is empty (`wardrobe["items"]` is `[]`) | Calls the LLM with a general styling prompt instead of a wardrobe-specific one. Returns general advice (what types of pieces pair well, overall vibe, styling tips) rather than crashing or returning empty string. |
| `create_fit_card` | `outfit` is empty or whitespace-only | Returns the error string "Cannot generate a fit card without an outfit suggestion. Please try the search again." without calling the LLM. |

**Concrete tested example — `search_listings` no-results path:**

```
$ python -c "from tools import search_listings; print(search_listings('designer ballgown', size='XXS', max_price=5))"
[]
```

Running the full agent with the same impossible query:
```
$ python agent.py
=== No-results path ===
Error message: No listings found for 'designer ballgown' in size XXS under $5.00.
Try broadening your search — remove the size filter, raise the price, or use different keywords.
```

The agent shows this error in the listing panel and leaves the outfit and fit card panels empty.

**Concrete tested example — `create_fit_card` empty outfit guard:**

```python
from tools import search_listings, create_fit_card
results = search_listings("vintage graphic tee", size=None, max_price=50)
print(create_fit_card("", results[0]))
# → "Cannot generate a fit card without an outfit suggestion. Please try the search again."
```

---

## Interaction Walkthrough

**User query:** "looking for a vintage graphic tee under $30"

**Step 1 — Tool called: LLM query parse**
- Input: the raw query string
- Why: Extract structured parameters (description, size, max_price) so `search_listings` can filter correctly
- Output: `{"description": "vintage graphic tee", "size": null, "max_price": 30.0}`

**Step 2 — Tool called: `search_listings`**
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why: Find matching secondhand listings within the user's budget
- Output: A list of matching listings (e.g., Y2K Baby Tee at $18, Graphic Tee bootleg style at $24). Top result stored in `session["selected_item"]`.

**Step 3 — Tool called: `suggest_outfit`**
- Input: `new_item={"title": "Y2K Baby Tee...", "price": 18.0, ...}`, `wardrobe={"items": [baggy jeans, chunky sneakers, ...]}`
- Why: User has an existing wardrobe on file; generate specific outfit combinations referencing named pieces
- Output: Two outfit suggestions referencing specific wardrobe pieces by name, with silhouette and styling notes. Stored in `session["outfit_suggestion"]`.

**Step 4 — Tool called: `create_fit_card`**
- Input: `outfit="Outfit 1: Pair the Y2K Baby Tee with your baggy straight-leg jeans..."`, `new_item={"title": "Y2K Baby Tee...", "price": 18.0, "platform": "depop"}`
- Why: Generate a shareable caption the user can post with their OOTD photos
- Output: "I'm obsessing over my new Y2K Baby Tee that I scored for $18 on Depop..." Stored in `session["fit_card"]`.

**Final output to user:**
- **Top listing found:** Y2K Baby Tee — Butterfly Print | $18.00 | Depop | Size: S/M | Condition: excellent
- **Outfit idea:** The two outfit suggestions from step 3
- **Your fit card:** The caption from step 4

---

## Spec Reflection

**One way planning.md helped during implementation:**

Writing out the planning loop's conditional logic in plain English before touching code made the branching structure obvious. The spec said: "After `search_listings` runs, check if results is empty. If yes, set error and return early." That sentence translated almost directly into the `if not session["search_results"]:` branch in `run_agent()`. Without the spec, it would have been tempting to pass an empty list into `suggest_outfit` and let it fail downstream — the spec made the correct early-exit behavior the obvious choice.

**One divergence from the spec, and why:**

The spec described the query parser as using LLM with a JSON-output prompt and a fallback to the full query on failure. In implementation, the fallback turned out to be more important than expected — early testing showed the model occasionally returned JSON with a `null` description field (when the query was very short). The code had to add explicit handling for `parsed.get("description") or query` to default back to the full query string. The spec described the fallback as a single line but the actual implementation needed a more defensive pattern throughout the parse step.

---

## AI Usage

**Instance 1 — Implementing `search_listings`:**

I gave Claude the Tool 1 spec from `planning.md` — the input parameters with types (description: str, size: str|None, max_price: float|None), the return value description (list[dict] sorted by keyword score), and the failure mode (return [] never raise). I asked it to implement the function using `load_listings()` from the data loader. The generated code scored by splitting description into words and checking presence in a concatenated text blob — I reviewed it against the spec and found it was skipping the `style_tags` field from scoring. I manually added `" ".join(listing.get("style_tags", []))` to the text concatenation before using the code. I also adjusted it to drop listings with score=0 rather than showing all price-filtered results.

**Instance 2 — Implementing the planning loop:**

I gave Claude the full Architecture ASCII diagram from `planning.md` plus the Planning Loop and State Management sections. I asked it to implement `run_agent()` in agent.py. The generated code was mostly correct but used `session["results"]` as the key name instead of `session["search_results"]` (which the spec and `_new_session()` defined). I caught this before running because I cross-checked the generated key names against `_new_session()`'s dict definition. I also revised the LLM parse prompt — the original generated version used `"size": "none"` (a string) when no size was mentioned, which would have passed a literal "none" string to the size filter. I changed the prompt to explicitly say `"size": null (JSON null, not the string "none")` to fix this before running any tests.
