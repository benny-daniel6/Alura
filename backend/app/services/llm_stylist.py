"""
AI Stylist engine for Alura.

Generates outfit suggestions from the user's real wardrobe, conditioned on weather, occasion,
style preferences, an optional free-text request and optional "must include" anchor pieces.

Engines:
- "gemini": Gemini structured JSON output (default when GEMINI_API_KEY is set)
- "openai": any OpenAI-compatible chat completions API (LLM_API_KEY)
- "rule_engine": deterministic scoring fallback, also used to top up / repair LLM results

Whatever the engine returns goes through `validate_outfit`, which enforces that every item exists
in the wardrobe, the category combination is wearable, anchors are included, and reports which
core pieces are missing when the wardrobe cannot complete a look.
"""

import json
import logging
import random
from datetime import datetime, timezone
from collections import Counter
from itertools import product
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.services.gemini import GeminiClient, gemini_client

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Wardrobe structure rules
# ------------------------------------------------------------------

ONE_PIECES = {"dress", "one_piece"}
SLOT_LIMITS = {
    "top": 1,
    "bottom": 1,
    "dress": 1,
    "one_piece": 1,
    "outerwear": 1,
    "footwear": 1,
    "headwear": 1,
    "bag": 1,
    "accessory": 2,
}
NEUTRALS = {"black", "white", "grey", "gray", "navy", "navy blue", "beige", "cream", "tan", "brown", "denim", "khaki"}

OCCASION_TITLES = {
    "office_work": "Polished Professional",
    "casual_daily": "Effortless Everyday",
    "evening_dinner": "Dinner-Ready Edit",
    "nightlife": "After-Dark Edit",
    "formal_events": "Formal Capsule",
    "athleisure": "Sport-Luxe Flow",
}
DRESSY_OCCASIONS = {"office_work", "formal_events", "evening_dinner"}


def _cat(item: Dict[str, Any]) -> str:
    return str(item.get("category") or "top")


def _color(item: Dict[str, Any]) -> str:
    return str(item.get("primary_color") or "").lower()


def validate_outfit(
    item_ids: Sequence[str],
    items_by_id: Dict[str, Dict[str, Any]],
    anchor_ids: Sequence[str] = (),
) -> Tuple[List[str], List[str]]:
    """
    Returns (cleaned_item_ids, missing_core_categories).
    Unknown IDs and duplicates are dropped, anchors are forced in first, per-category limits are applied,
    and a dress/one-piece displaces separates (unless a separate is an anchor, which then wins).
    """
    ordered: List[str] = []
    for iid in list(anchor_ids) + list(item_ids):
        iid = str(iid)
        if iid in items_by_id and iid not in ordered:
            ordered.append(iid)

    anchors = {str(a) for a in anchor_ids}
    anchored_cats = {_cat(items_by_id[a]) for a in anchors if a in items_by_id}
    separates_anchored = bool(anchored_cats & {"top", "bottom"})
    has_one_piece = any(_cat(items_by_id[i]) in ONE_PIECES for i in ordered)

    kept: List[str] = []
    counts: Dict[str, int] = {}
    one_piece_kept = False
    for iid in ordered:
        cat = _cat(items_by_id[iid])
        if cat in ONE_PIECES:
            if separates_anchored or one_piece_kept:
                continue
            one_piece_kept = True
        elif cat in ("top", "bottom") and has_one_piece and not separates_anchored and iid not in anchors:
            continue
        limit = SLOT_LIMITS.get(cat, 1)
        if counts.get(cat, 0) >= limit:
            continue
        counts[cat] = counts.get(cat, 0) + 1
        kept.append(iid)

    cats = {_cat(items_by_id[i]) for i in kept}
    if cats & ONE_PIECES:
        missing: List[str] = []
    else:
        missing = [c for c in ("top", "bottom") if c not in cats]
    return kept, missing


# ------------------------------------------------------------------
# Scoring (rule engine)
# ------------------------------------------------------------------


def _target_seasons(weather: Dict[str, Any]) -> set:
    temp = weather.get("temperature_c", 20.0)
    if temp < 10:
        return {"winter", "fall", "all_season"}
    if temp < 18:
        return {"fall", "spring", "all_season"}
    if temp < 26:
        return {"spring", "summer", "all_season"}
    return {"summer", "all_season"}


def _days_since(value: Any, now: datetime) -> Optional[float]:
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return (now - value).total_seconds() / 86400


# Garment knowledge for the rule engine, matched against an item's name/sub-category (first match wins).
# (keywords, formality 0 casual .. 3 formal, warmth -1 light .. 2 heavy, sporty)
GARMENT_TRAITS: List[Tuple[Tuple[str, ...], float, float, bool]] = [
    (("blazer", "suit jacket"), 3.0, 1.0, False),
    (("trench", "overcoat", "parka", "puffer", "coat"), 2.0, 2.0, False),
    (("leather jacket",), 1.5, 1.5, False),
    (("denim jacket",), 0.5, 1.0, False),
    (("hoodie", "sweatshirt"), 0.0, 1.5, True),
    (("cardigan", "sweater", "jumper", "knit"), 1.5, 1.5, False),
    (("windbreaker",), 0.3, 0.5, True),
    (("jacket",), 1.5, 1.0, False),
    (("button-up", "oxford shirt", "dress shirt", "formal shirt"), 2.5, 0.0, False),
    (("blouse",), 2.0, 0.0, False),
    (("polo",), 1.5, 0.0, False),
    (("tank top", "crop top", "camisole"), 0.3, -1.0, False),
    (("t-shirt", "tee"), 0.5, -0.5, False),
    (("shirt",), 1.8, 0.0, False),
    (("shorts",), 0.0, -1.0, True),
    (("leggings", "joggers", "track pants"), 0.0, 0.0, True),
    (("chinos", "slacks", "trousers"), 2.2, 0.0, False),
    (("jeans", "denim"), 1.0, 0.0, False),
    (("skirt",), 1.5, 0.0, False),
    (("pants",), 1.8, 0.0, False),
    (("gown",), 3.0, 0.0, False),
    (("dress",), 2.0, 0.0, False),
    (("loafers", "oxfords", "derby", "brogues", "high heels", "heels"), 2.8, 0.0, False),
    (("sandals", "flip flops", "slides"), 0.3, -1.0, False),
    (("sneakers", "trainers", "running shoes"), 0.5, 0.0, True),
    (("boots",), 1.5, 1.0, False),
    (("clutch",), 2.5, 0.0, False),
    (("handbag", "shoulder bag", "purse", "tote"), 1.8, 0.0, False),
    (("backpack",), 0.3, 0.0, True),
    (("necktie", " tie "), 3.0, 0.0, False),
    (("scarf",), 1.5, 1.5, False),
    (("belt",), 1.8, 0.0, False),
    (("watch",), 2.0, 0.0, False),
    (("beanie",), 0.5, 1.5, False),
    (("baseball cap", " cap "), 0.0, 0.0, True),
    (("hat",), 1.0, 0.0, False),
]
CATEGORY_DEFAULT_TRAITS = {
    "top": (1.0, 0.0), "bottom": (1.5, 0.0), "outerwear": (1.5, 1.0), "dress": (2.0, 0.0), "one_piece": (1.0, 0.0),
    "footwear": (1.0, 0.0), "bag": (1.0, 0.0), "accessory": (1.5, 0.0), "headwear": (0.5, 0.0),
}
OCCASION_FORMALITY = {
    "athleisure": 0.0, "casual_daily": 1.0, "nightlife": 1.5, "evening_dinner": 2.0, "office_work": 2.3,
    "formal_events": 3.0,
}


def garment_traits(item: Dict[str, Any]) -> Tuple[float, float, bool]:
    text = f" {item.get('name') or ''} {item.get('sub_category') or ''} ".lower()
    for keywords, formality, warmth, sporty in GARMENT_TRAITS:
        if any(k in text for k in keywords):
            return formality, warmth, sporty
    formality, warmth = CATEGORY_DEFAULT_TRAITS.get(_cat(item), (1.0, 0.0))
    return formality, warmth, False


def score_item(item: Dict[str, Any], weather: Dict[str, Any], occasion: str, preferences: Dict[str, Any], now: datetime) -> float:
    score = 0.0
    formality, warmth, sporty = garment_traits(item)

    # Occasion: explicit tags (from Gemini or the user) win; otherwise judge by garment formality
    occasions = item.get("occasions") or []
    if occasion in occasions:
        score += 2.0
    elif occasions:
        score -= 0.5
    target = OCCASION_FORMALITY.get(occasion, 1.0)
    score += 1.2 - 0.9 * abs(formality - target)
    if occasion == "athleisure" and sporty:
        score += 1.0

    # Weather: season tags plus garment warmth
    seasons = set(item.get("seasons") or ["all_season"])
    score += 0.5 if seasons & _target_seasons(weather) else -1.0
    temp = weather.get("temperature_c", 20.0)
    if temp >= 26:
        score -= 2.0 if warmth >= 1 else 0.0
        score += 0.4 if warmth < 0 else 0.0
    elif temp < 12:
        score -= 3.0 if warmth < 0 else 0.0  # shorts / sandals in the cold beat even a sporty bonus
        score += 0.6 if warmth >= 1 else 0.0

    color = _color(item)
    preferred = {c.lower() for c in preferences.get("preferred_colors") or []}
    avoided = {c.lower() for c in preferences.get("avoided_colors") or []}
    if color and color in avoided:
        score -= 5.0
    if color and (color in preferred or ("neutrals" in preferred and color in NEUTRALS)):
        score += 0.5
    days = _days_since(item.get("last_worn_at"), now)
    if days is not None and days < 3:
        score -= 1.5 * (3 - days) / 3
    if item.get("is_favorite"):
        score += 0.3
    return score


def _pair_harmony(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ca, cb = _color(a), _color(b)
    if not ca or not cb:
        return 0.0
    if ca in NEUTRALS or cb in NEUTRALS:
        return 0.6
    if ca == cb:
        return 0.1  # tonal, fine but less interesting
    return -0.4  # two competing statement colours


# ------------------------------------------------------------------
# Prompting
# ------------------------------------------------------------------

SYSTEM_PROMPT = """You are Alura, an expert personal fashion stylist. You build outfits ONLY from the user's own wardrobe.

Rules:
1. Reference wardrobe pieces ONLY by their ref code (e.g. "i3") from the inventory. Never invent pieces.
2. A complete outfit has a top + a bottom, OR a dress / one-piece. Add outerwear, footwear, a bag, headwear or up to 2 accessories when they improve the look. Never combine a dress/one-piece with a top+bottom.
3. Every "must include" piece must appear in every outfit.
4. Dress for the weather (layers when cold, breathable when hot, outerwear and suitable shoes in rain), the occasion and the user's request and style.
5. Prefer colour harmony, avoid the user's avoided colours, and rotate: avoid pieces worn in the last 2 days unless essential. Make the outfits clearly different from each other.
6. If the wardrobe lacks something an outfit needs, still propose the best look possible and list what to add in "missing_pieces" (generic descriptions, e.g. "slim dark chinos").
7. rationale: 2-3 warm, specific sentences on why it works. styling_tips: 1-3 short practical tips (tuck, roll sleeves, accessorise).
"""

USER_PROMPT_TEMPLATE = """## Weather
{weather_snippet}

## Occasion
{occasion}

## User request
{request}

## Style profile
- Style vibes: {style_vibes}
- Preferred colours: {preferred_colors}
- Avoided colours: {avoided_colors}
- Fit preference: {sizing_preference}

## Must include
{anchors}

## Wardrobe inventory ({item_count} pieces)
{wardrobe_manifest}

Suggest {num_outfits} outfit(s)."""

OUTFIT_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "outfits": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "name": {"type": "STRING", "description": "Editorial outfit title, max 5 words"},
                    "item_refs": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "rationale": {"type": "STRING"},
                    "styling_tips": {"type": "ARRAY", "items": {"type": "STRING"}},
                    "missing_pieces": {"type": "ARRAY", "items": {"type": "STRING"}},
                },
                "required": ["name", "item_refs", "rationale"],
            },
        }
    },
    "required": ["outfits"],
}


def _look_name(core: List[Dict[str, Any]]) -> str:
    """Short descriptive title from the core pieces, e.g. "Button-up shirt & chinos"."""
    types = []
    for piece in core:
        kind = (piece.get("sub_category") or _cat(piece)).strip().lower()
        if kind and kind not in types:
            types.append(kind)
    title = " & ".join(types[:2])
    return title[:1].upper() + title[1:] if title else ""


def _humanize(value: str) -> str:
    return value.replace("_", " ")


class LLMStylistService:
    """Generates outfit suggestions; see module docstring for engines."""

    def __init__(
        self,
        provider: Optional[str] = None,
        gemini: Optional[GeminiClient] = None,
        api_key: Optional[str] = None,
        api_base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 45.0,
        seed: Optional[int] = None,
    ):
        self.provider = (provider or settings.STYLIST_PROVIDER).lower()
        self.gemini = gemini or gemini_client
        self.api_key = settings.LLM_API_KEY if api_key is None else api_key
        self.api_base_url = (api_base_url or settings.LLM_API_BASE_URL).rstrip("/")
        self.model = model or settings.LLM_MODEL
        self.timeout = timeout
        # Small per-request jitter so "Restyle" varies between near-equal looks; seed it for reproducible tests
        self._rng = random.Random(seed)

    @property
    def active_engine(self) -> str:
        if self.provider == "gemini" and self.gemini.enabled:
            return "gemini"
        if self.provider == "openai" and self.api_key:
            return "openai"
        return "rule_engine"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def suggest_outfits(
        self,
        wardrobe_items: List[Dict[str, Any]],
        weather: Dict[str, Any],
        occasion: str,
        preferences: Dict[str, Any],
        num_outfits: int = 3,
        user_request: Optional[str] = None,
        anchor_ids: Sequence[str] = (),
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Returns (outfits, engine_used). Each outfit dict has:
        name, item_ids, occasion, rationale, styling_tips, missing_categories, missing_pieces, is_complete
        """
        if not wardrobe_items:
            return [], "rule_engine"

        items_by_id = {str(i["id"]): i for i in wardrobe_items}
        anchor_ids = [str(a) for a in anchor_ids if str(a) in items_by_id]
        engine = self.active_engine
        outfits: List[Dict[str, Any]] = []

        if engine != "rule_engine":
            try:
                raw = await self._llm_suggest(
                    engine, wardrobe_items, weather, occasion, preferences, num_outfits, user_request, anchor_ids
                )
                outfits = self._finalize(raw, items_by_id, anchor_ids, occasion)
            except Exception as e:
                logger.error(f"{engine} stylist failed: {e}. Falling back to rule engine.")
                engine = "rule_engine"

        if len(outfits) < num_outfits:
            rules = self._rule_based_suggest(wardrobe_items, weather, occasion, preferences, num_outfits, anchor_ids)
            seen = {frozenset(o["item_ids"]) for o in outfits}
            for o in rules:
                if len(outfits) >= num_outfits:
                    break
                if frozenset(o["item_ids"]) not in seen:
                    seen.add(frozenset(o["item_ids"]))
                    outfits.append(o)
            if not outfits:
                engine = "rule_engine"

        return outfits[:num_outfits], engine

    def _finalize(
        self,
        raw_outfits: List[Dict[str, Any]],
        items_by_id: Dict[str, Dict[str, Any]],
        anchor_ids: Sequence[str],
        occasion: str,
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen = set()
        for o in raw_outfits:
            ids, missing = validate_outfit(o.get("item_ids", []), items_by_id, anchor_ids)
            if not ids or frozenset(ids) in seen:
                continue
            seen.add(frozenset(ids))
            result.append({
                "name": (o.get("name") or "Curated Look").strip()[:80],
                "item_ids": ids,
                "occasion": occasion,
                "rationale": (o.get("rationale") or "A considered combination from your wardrobe.").strip(),
                "styling_tips": [t.strip() for t in o.get("styling_tips") or [] if t and t.strip()][:3],
                "missing_categories": missing,
                "missing_pieces": [p.strip() for p in o.get("missing_pieces") or [] if p and p.strip()][:3],
                "is_complete": not missing,
            })
        return result

    # ------------------------------------------------------------------
    # LLM engines
    # ------------------------------------------------------------------

    def _build_prompts(
        self,
        wardrobe_items: List[Dict[str, Any]],
        weather: Dict[str, Any],
        occasion: str,
        preferences: Dict[str, Any],
        num_outfits: int,
        user_request: Optional[str],
        anchor_ids: Sequence[str],
    ) -> Tuple[str, Dict[str, str]]:
        from app.services.weather import WeatherService

        # Short refs instead of UUIDs: fewer tokens and far fewer copy errors
        ref_to_id = {f"i{n}": str(item["id"]) for n, item in enumerate(wardrobe_items, start=1)}
        id_to_ref = {v: k for k, v in ref_to_id.items()}
        now = datetime.now(timezone.utc)
        manifest = self._build_wardrobe_manifest(wardrobe_items, id_to_ref, now)
        anchors = (
            "\n".join(f"- {id_to_ref[a]}" for a in anchor_ids) if anchor_ids else "Nothing specific."
        )
        prompt = USER_PROMPT_TEMPLATE.format(
            weather_snippet=WeatherService.weather_to_prompt_snippet(weather),
            occasion=_humanize(occasion),
            request=(user_request or "").strip() or "No extra request.",
            style_vibes=", ".join(preferences.get("style_vibes") or []) or "not specified",
            preferred_colors=", ".join(preferences.get("preferred_colors") or []) or "not specified",
            avoided_colors=", ".join(preferences.get("avoided_colors") or []) or "none",
            sizing_preference=preferences.get("sizing_preference") or "regular",
            anchors=anchors,
            wardrobe_manifest=manifest,
            item_count=len(wardrobe_items),
            num_outfits=num_outfits,
        )
        return prompt, ref_to_id

    async def _llm_suggest(
        self,
        engine: str,
        wardrobe_items: List[Dict[str, Any]],
        weather: Dict[str, Any],
        occasion: str,
        preferences: Dict[str, Any],
        num_outfits: int,
        user_request: Optional[str],
        anchor_ids: Sequence[str],
    ) -> List[Dict[str, Any]]:
        prompt, ref_to_id = self._build_prompts(
            wardrobe_items, weather, occasion, preferences, num_outfits, user_request, anchor_ids
        )
        if engine == "gemini":
            parsed = await self.gemini.generate_json(SYSTEM_PROMPT, prompt, OUTFIT_SCHEMA, temperature=0.9)
        else:
            parsed = await self._openai_json(prompt)

        outfits = parsed.get("outfits", []) if isinstance(parsed, dict) else []
        for o in outfits:
            refs = o.get("item_refs") or o.get("item_ids") or []
            o["item_ids"] = [ref_to_id.get(str(r).strip(), str(r).strip()) for r in refs]
        return outfits

    async def _openai_json(self, prompt: str) -> Dict[str, Any]:
        import httpx

        schema_hint = (
            '\nReturn ONLY JSON: {"outfits": [{"name": str, "item_refs": [str], "rationale": str, '
            '"styling_tips": [str], "missing_pieces": [str]}]}'
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT + schema_hint},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.api_base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(content)

    # ------------------------------------------------------------------
    # Rule-based engine
    # ------------------------------------------------------------------

    def _rule_based_suggest(
        self,
        wardrobe_items: List[Dict[str, Any]],
        weather: Dict[str, Any],
        occasion: str,
        preferences: Dict[str, Any],
        num_outfits: int,
        anchor_ids: Sequence[str] = (),
    ) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        items_by_id = {str(i["id"]): i for i in wardrobe_items}
        scores = {
            iid: score_item(i, weather, occasion, preferences, now) + self._rng.uniform(-0.25, 0.25)
            for iid, i in items_by_id.items()
        }
        anchors = [a for a in anchor_ids if a in items_by_id]
        anchor_cats = {_cat(items_by_id[a]) for a in anchors}

        def pool(*cats: str) -> List[Dict[str, Any]]:
            found = [i for i in wardrobe_items if _cat(i) in cats]
            # An anchored category is fixed to the anchor
            pinned = [items_by_id[a] for a in anchors if _cat(items_by_id[a]) in cats]
            chosen = pinned or found
            return sorted(chosen, key=lambda i: scores[str(i["id"])], reverse=True)

        tops, bottoms, dresses = pool("top"), pool("bottom"), pool("dress", "one_piece")
        separates_pinned = bool(anchor_cats & {"top", "bottom"})
        one_piece_pinned = bool(anchor_cats & ONE_PIECES)

        # Candidate bases: (item list, score)
        bases: List[Tuple[List[Dict[str, Any]], float]] = []
        if not one_piece_pinned:
            for t, b in product(tops[:10], bottoms[:10]):
                s = scores[str(t["id"])] + scores[str(b["id"])] + _pair_harmony(t, b)
                bases.append(([t, b], s))
        if not separates_pinned:
            for d in dresses[:10]:
                bases.append(([d], scores[str(d["id"])] * 2 + 0.4))
        if not bases:
            # Incomplete wardrobe (e.g. only tops): style what exists and say what is missing
            singles = (tops or bottoms)[:max(num_outfits, 1)]
            bases = [([s], scores[str(s["id"])]) for s in singles]

        temp = weather.get("temperature_c", 20.0)
        outerwear_pool = pool("outerwear")
        smart_layer = any(garment_traits(o)[0] >= 2.5 for o in outerwear_pool)
        need_layer = (
            temp < 18
            or (weather.get("is_rainy") and temp < 24)
            or (occasion in {"office_work", "formal_events"} and temp < 26 and smart_layer)
        )
        extras = {
            "outerwear": outerwear_pool if need_layer or "outerwear" in anchor_cats else [],
            "footwear": pool("footwear"),
            "bag": pool("bag"),
            "accessory": pool("accessory"),
            "headwear": pool("headwear") if "headwear" in anchor_cats or temp < 8 or occasion == "athleisure" else [],
        }

        # Greedy selection with a reuse penalty, so the looks in one response use different pieces
        usage: Counter = Counter()
        reuse_penalty = 1.6
        outfits: List[Dict[str, Any]] = []
        remaining = list(bases)
        while remaining and len(outfits) < num_outfits:
            best = max(
                remaining,
                key=lambda b: b[1] - reuse_penalty * sum(usage[str(i["id"])] for i in b[0] if str(i["id"]) not in anchors),
            )
            remaining.remove(best)
            chosen = list(best[0])
            for cat, options in extras.items():
                pinned = [o for o in options if str(o["id"]) in anchors]
                if pinned:
                    chosen.append(pinned[0])
                    continue
                if not options:
                    continue
                pick = max(options, key=lambda o: scores[str(o["id"])] - reuse_penalty * usage[str(o["id"])])
                # Optional pieces only when they suit the look; layers and shoes are always worth adding
                if cat in ("bag", "accessory", "headwear") and scores[str(pick["id"])] < 0:
                    continue
                chosen.append(pick)
            ids, missing = validate_outfit([str(i["id"]) for i in chosen], items_by_id, anchors)
            if any(set(ids) == set(o["item_ids"]) for o in outfits):
                continue
            usage.update(ids)
            outfits.append(self._describe_rule_outfit(ids, missing, items_by_id, weather, occasion, len(outfits)))
        return outfits

    @staticmethod
    def _describe_rule_outfit(
        ids: List[str],
        missing: List[str],
        items_by_id: Dict[str, Dict[str, Any]],
        weather: Dict[str, Any],
        occasion: str,
        index: int,
    ) -> Dict[str, Any]:
        pieces = [items_by_id[i] for i in ids]

        def label(i: Dict[str, Any]) -> str:
            return (i.get("name") or i.get("sub_category") or _cat(i)).strip()

        core = [p for p in pieces if _cat(p) in ("top", "bottom", "dress", "one_piece")]
        layers = [p for p in pieces if _cat(p) == "outerwear"]
        parts = []
        if len(core) == 2:
            parts.append(f"The {label(core[0]).lower()} pairs cleanly with the {label(core[1]).lower()}")
        elif core:
            parts.append(f"Built around your {label(core[0]).lower()}")
        if layers:
            reason = "against the rain" if weather.get("is_rainy") else "for warmth" if weather.get("temperature_c", 20) < 16 else "for polish"
            parts.append(f"with the {label(layers[0]).lower()} layered on {reason}")
        rationale = " ".join(parts) + "."
        condition = str(weather.get("condition", ""))
        if condition and "fallback" not in condition.lower():
            rationale += f" Chosen for {_humanize(occasion)} in {condition.lower()} at {round(weather.get('temperature_c', 20))}°C."
        else:
            rationale += f" Chosen for {_humanize(occasion)}."

        tips = []
        if any(_cat(p) == "top" for p in pieces) and occasion in DRESSY_OCCASIONS:
            tips.append("Tuck the top in for a sharper line.")
        if weather.get("is_hot"):
            tips.append("Keep accessories minimal so the look stays light.")
        missing_pieces = []
        if "bottom" in missing:
            missing_pieces.append("a versatile neutral bottom, like dark chinos or straight jeans")
        if "top" in missing:
            missing_pieces.append("a simple neutral top, like a white tee or oxford shirt")

        return {
            "name": _look_name(core) or f"{OCCASION_TITLES.get(occasion, 'Curated Look')} #{index + 1}",
            "item_ids": ids,
            "occasion": occasion,
            "rationale": rationale,
            "styling_tips": tips,
            "missing_categories": missing,
            "missing_pieces": missing_pieces,
            "is_complete": not missing,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_wardrobe_manifest(
        items: List[Dict[str, Any]], id_to_ref: Dict[str, str], now: Optional[datetime] = None
    ) -> str:
        """Format wardrobe items into a concise manifest for the LLM prompt."""
        now = now or datetime.now(timezone.utc)
        lines = []
        for item in items:
            colors = "/".join(c for c in (item.get("primary_color"), item.get("secondary_color")) if c) or "unknown"
            days = _days_since(item.get("last_worn_at"), now)
            worn = "never worn" if days is None else f"last worn {int(days)}d ago"
            line = (
                f"- {id_to_ref[str(item['id'])]} | {item.get('name') or 'unnamed'} | {_cat(item)}"
                f" | {item.get('sub_category') or '-'} | colour: {colors}"
                f" | seasons: {', '.join(item.get('seasons') or ['all_season'])}"
                f" | occasions: {', '.join(item.get('occasions') or []) or 'any'} | {worn}"
                f"{' | favourite' if item.get('is_favorite') else ''}"
            )
            lines.append(line)
        return "\n".join(lines)


# Module-level singleton
llm_stylist_service = LLMStylistService()
