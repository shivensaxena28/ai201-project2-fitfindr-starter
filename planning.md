# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items matching a keyword description, optional size, and optional price ceiling. Returns a sorted list of matching listing dicts, best match first.

**Input parameters:**
- `description` (str): Keywords describing the item to search for (e.g., "vintage graphic tee"). Matched against title, description text, style_tags, and category fields.
- `size` (str): Size string to filter by, or None to skip size filtering. Case-insensitive substring match (e.g., "M" matches "S/M" and "M").
- `max_price` (float): Maximum price inclusive (e.g., 30.0), or None to skip price filtering.

**What it returns:**
A list of listing dicts sorted by relevance score (highest first). Each dict has these fields: `id` (str), `title` (str), `description` (str), `category` (str — one of tops, bottoms, outerwear, shoes, accessories), `style_tags` (list[str]), `size` (str), `condition` (str — excellent/good/fair), `price` (float), `colors` (list[str]), `brand` (str or None), `platform` (str — depop/thredUp/poshmark). Returns an empty list `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to: "No listings found for '[description]' in size [size] under $[max_price]. Try broadening your search — remove the size filter, raise the price, or use different keywords." Then it returns the session immediately without calling suggest_outfit or create_fit_card.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted item and the user's current wardrobe, calls the LLM to suggest 1–2 complete outfit combinations. If the wardrobe is empty, returns general styling advice for the item instead.

**Input parameters:**
- `new_item` (dict): A listing dict for the item the user is considering (the top result from search_listings). Contains title, description, style_tags, colors, price, platform, and other fields.
- `wardrobe` (dict): A wardrobe dict with an `items` key containing a list of wardrobe item dicts. Each wardrobe item has: `id`, `name`, `category`, `colors`, `style_tags`, `notes`. May have an empty `items` list.

**What it returns:**
A non-empty string with 1–2 outfit suggestions. If the wardrobe has items, the suggestions reference specific named pieces from the wardrobe. If the wardrobe is empty, the string contains general styling advice for the item (what vibes it suits, what types of pieces pair well). Never returns an empty string — always returns a useful text response.

**What happens if it fails or returns nothing:**
If the LLM call raises an exception, the function catches it and returns: "Could not generate outfit suggestion (LLM error). Try searching for a different item or check your API key." The agent stores this string in `session["outfit_suggestion"]` and continues to create_fit_card with it — it is a degraded but not crashed state.

---

### Tool 3: create_fit_card

**What it does:**
Generates a short, shareable 2–4 sentence outfit caption for the thrifted find — something the user could post on Instagram or TikTok. Uses a higher LLM temperature so each call produces a distinct result.

**Input parameters:**
- `outfit` (str): The outfit suggestion string returned by suggest_outfit(). Must be non-empty.
- `new_item` (dict): The listing dict for the thrifted item. Used for item name, price, and platform details.

**What it returns:**
A 2–4 sentence string written in casual first-person tone, like a real OOTD caption. Mentions the item name, price, and platform naturally (once each). Captures the outfit vibe in specific terms. Sounds different each call for different inputs. If `outfit` is empty or whitespace-only, returns the error string: "Cannot generate a fit card without an outfit suggestion. Please try the search again."

**What happens if it fails or returns nothing:**
If `outfit` is empty, returns the error string above without calling the LLM. If the LLM call raises an exception, catches it and returns: "Fit card generation failed — but here's what you found: [item title] for $[price] on [platform]." The agent always stores whatever string is returned in `session["fit_card"]`.

---

### Additional Tools (if any)

None beyond the three required tools.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop in `run_agent()` follows this conditional logic:

1. **Initialize session** — call `_new_session(query, wardrobe)` to set up the state dict.

2. **Parse the query** — call the LLM with a structured prompt asking it to extract three fields from the natural language query: `description` (str), `size` (str or null), and `max_price` (float or null). Store the parsed result in `session["parsed"]`. If parsing fails, default to using the full query as description with no size/price filter.

3. **Call search_listings** — use `session["parsed"]["description"]`, `session["parsed"]["size"]`, and `session["parsed"]["max_price"]` as arguments. Store results in `session["search_results"]`.
   - **Branch: results is empty** → set `session["error"]` to a specific message naming what was searched and suggesting alternatives. **Return session immediately.** Do NOT call suggest_outfit or create_fit_card.
   - **Branch: results is non-empty** → set `session["selected_item"] = results[0]` and continue.

4. **Call suggest_outfit** — pass `session["selected_item"]` and `session["wardrobe"]`. Store the returned string in `session["outfit_suggestion"]`.

5. **Call create_fit_card** — pass `session["outfit_suggestion"]` and `session["selected_item"]`. Store the returned string in `session["fit_card"]`.

6. **Return session** — `session["error"]` remains None for a successful run.

The loop terminates early only if search_listings returns no results. In all other cases (including LLM errors in suggest_outfit or create_fit_card), the loop completes all three steps and returns whatever the tools produced.

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict initialized by `_new_session()`. The dict has these keys:
- `query` (str): the original user query, never modified
- `parsed` (dict): extracted `description`, `size`, `max_price` from the query
- `search_results` (list[dict]): all matching listing dicts from search_listings
- `selected_item` (dict or None): `search_results[0]`, the item passed into suggest_outfit
- `wardrobe` (dict): the user's wardrobe dict, passed into suggest_outfit
- `outfit_suggestion` (str or None): the string returned by suggest_outfit, passed into create_fit_card
- `fit_card` (str or None): the final caption string from create_fit_card
- `error` (str or None): set if the interaction terminated early; None on success

The session dict is passed by reference through the loop — each step reads from and writes to the same dict. No data is duplicated or re-requested from the user between steps.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query (empty list returned) | Sets `session["error"]` to: "No listings found for '[description]' in size [size] under $[max_price]. Try broadening your search — remove the size filter, raise the price, or use different keywords." Returns early; suggest_outfit and create_fit_card are not called. |
| suggest_outfit | Wardrobe is empty (`wardrobe["items"]` is an empty list) | Calls the LLM with a general styling prompt instead of a wardrobe-specific one. Returns general advice like "This piece suits a streetwear or casual look — try pairing it with wide-leg jeans, chunky sneakers, and a minimal jacket." Never crashes. |
| create_fit_card | Outfit input is missing or empty string | Returns the error string "Cannot generate a fit card without an outfit suggestion. Please try the search again." without calling the LLM. |

---

## Architecture

```
User query (natural language)
    │
    ▼
run_agent(query, wardrobe)
    │
    ├─ Step 1: _new_session(query, wardrobe)
    │          → session dict initialized
    │
    ├─ Step 2: LLM parse query
    │          → session["parsed"] = {description, size, max_price}
    │
    ├─ Step 3: search_listings(description, size, max_price)
    │          → session["search_results"] = [...]
    │
    │   ┌── results == [] ──────────────────────────────────────────┐
    │   │   session["error"] = "No listings found..."               │
    │   │   return session  ◄──────────────────── EARLY EXIT        │
    │   └───────────────────────────────────────────────────────────┘
    │
    │   results non-empty:
    │   session["selected_item"] = results[0]
    │
    ├─ Step 4: suggest_outfit(selected_item, wardrobe)
    │          │
    │          ├── wardrobe["items"] == [] → general styling advice (no crash)
    │          └── wardrobe non-empty    → specific combos using named pieces
    │          → session["outfit_suggestion"] = "..."
    │
    ├─ Step 5: create_fit_card(outfit_suggestion, selected_item)
    │          │
    │          ├── outfit == "" → return error string (no LLM call)
    │          └── outfit non-empty → LLM caption (high temperature)
    │          → session["fit_card"] = "..."
    │
    └─ Step 6: return session
                │
                ▼
           handle_query() in app.py
                │
                ├── session["error"] set → show error in listing panel, empty outfit/fitcard
                └── success → format selected_item + outfit_suggestion + fit_card
                              → 3 Gradio output panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **search_listings**: I gave Claude the Tool 1 spec from planning.md (input parameters with types, return value structure including all fields, failure mode). I asked it to implement `search_listings()` in tools.py using `load_listings()` from data_loader. Before running, I verified the generated code: (1) filtered by price and size separately, (2) scored by splitting description into words and checking overlap with title + description + style_tags, (3) handled the empty-results case by returning `[]`. I tested it with 3 queries: a valid search, an impossible query, and a price-only filter.

- **suggest_outfit**: I gave Claude the Tool 2 spec (inputs including wardrobe schema structure, return value, empty-wardrobe failure mode) plus the `wardrobe_schema.json` contents. I asked it to implement `suggest_outfit()` calling Groq's llama-3.3-70b-versatile. I verified the generated code had a branch for `len(wardrobe["items"]) == 0` with a distinct general-styling prompt, and that it caught LLM exceptions. I tested with both `get_example_wardrobe()` and `get_empty_wardrobe()`.

- **create_fit_card**: I gave Claude the Tool 3 spec (style guidelines: casual, first-person, mentions price/platform once, sounds different each call) and asked it to implement `create_fit_card()` with a temperature of 1.2. I verified the empty-outfit guard was first, the prompt mentioned all three style requirements, and I ran it twice on the same input to confirm different outputs.

**Milestone 4 — Planning loop and state management:**

I gave Claude the full Architecture diagram from planning.md (the ASCII diagram above) plus the Planning Loop and State Management sections. I asked it to implement `run_agent()` in agent.py. I verified before running: (1) the code branched on `len(session["search_results"]) == 0` and returned early, (2) `session["selected_item"]` was set to `results[0]` not re-derived, (3) the LLM parse step used a JSON-output prompt. I revised the LLM parse prompt to include explicit fallback defaults when the model returns null values.

---

## A Complete Interaction (Step by Step)

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
The agent calls the LLM to parse the query. The LLM extracts: `description = "vintage graphic tee"`, `size = None` (no size mentioned), `max_price = 30.0`. These are stored in `session["parsed"]`.

**Step 2:**
`search_listings("vintage graphic tee", size=None, max_price=30.0)` is called. It loads all listings, filters to those with `price <= 30.0`, then scores each by word overlap with "vintage graphic tee" against title/description/style_tags. The top result is `lst_006`: "Graphic Tee — 2003 Tour Bootleg Style" at $24 on Depop. This is stored in `session["search_results"]` and `session["selected_item"]`.

**Step 3:**
`suggest_outfit(new_item=lst_006, wardrobe=get_example_wardrobe())` is called. The wardrobe has 10 items, so the LLM receives a prompt listing them (baggy straight-leg jeans, chunky white sneakers, black combat boots, etc.) and asks for specific outfit combinations with the graphic tee. The LLM returns: "Outfit 1: Pair the bootleg graphic tee with your baggy straight-leg jeans and chunky white sneakers for a classic 90s streetwear look — tuck the front corner slightly and let the back hang loose. Outfit 2: Layer it under your vintage black denim jacket with the black combat boots for a grungier take." Stored in `session["outfit_suggestion"]`.

**Step 4:**
`create_fit_card(outfit=session["outfit_suggestion"], new_item=lst_006)` is called. The LLM generates a casual caption at high temperature: "thrifted this faded bootleg tee off depop for $24 and it was literally made for my wide-legs 🖤 styled it two ways this week and both slapped — full looks in my stories". Stored in `session["fit_card"]`.

**Final output to user:**
The Gradio UI shows three panels:
- **Top listing found**: "Graphic Tee — 2003 Tour Bootleg Style | $24.00 | Depop | Size: L | Condition: good | Colors: black | Tags: graphic tee, vintage, grunge, streetwear, band tee"
- **Outfit idea**: The two-outfit suggestion from Step 3
- **Your fit card**: The caption from Step 4

**Error path (no results):**
If the user had searched "designer ballgown size XXS under $5", search_listings would return `[]`. The agent sets `session["error"] = "No listings found for 'designer ballgown' in size XXS under $5.00. Try broadening your search — remove the size filter, raise the price, or use different keywords."` and returns immediately. The Gradio UI shows the error message in the listing panel and empty strings for outfit and fit card.
