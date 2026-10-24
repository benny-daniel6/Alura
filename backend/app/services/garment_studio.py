"""
Gemini-powered garment "studio": turns a casual phone photo into an e-commerce style product shot
on a pure white background, and tags the garment with structured metadata.

Both functions raise GeminiError on failure; the worker falls back to the local pipeline.
"""

import io
import logging
from typing import Any, Dict, Optional

from PIL import Image, ImageOps

from app.models.wardrobe import ClothingCategory
from app.services.gemini import GeminiClient, gemini_client

logger = logging.getLogger(__name__)

OCCASIONS = ["office_work", "casual_daily", "evening_dinner", "nightlife", "formal_events", "athleisure"]
SEASONS = ["spring", "summer", "fall", "winter", "all_season"]
COLORS = [
    "black", "white", "grey", "navy", "blue", "light blue", "beige", "cream", "brown", "tan",
    "olive", "green", "red", "burgundy", "pink", "purple", "yellow", "orange", "multicolor",
]

SHOWCASE_PROMPT = """Turn this photo into a professional e-commerce product photo of the garment, like a listing on Amazon or Zara.

Requirements:
- Show ONLY the main garment. Remove the background, people, hands, hangers, mannequins, furniture, bedding and every other object.
- Pure white background (#FFFFFF), soft even studio lighting, a very subtle shadow beneath the garment.
- Present it neatly as an ironed flat lay or invisible "ghost mannequin" shot, front view, centered, fully in frame with some margin.
- Keep the garment IDENTICAL to the photo: same colors, print and pattern, logos, text, buttons, collar, pockets, trims, fabric texture and proportions. Do not invent, recolor or restyle anything.
- Do not add text, watermarks, labels or props.
"""

TAG_SYSTEM = """You are a fashion cataloguing assistant. Describe the single main garment in the photo for a digital wardrobe.
Be precise and concise. Only describe what is visible."""

TAG_PROMPT = "Catalogue this garment."

TAG_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "name": {"type": "STRING", "description": "Short product title, max 6 words, e.g. 'Pink camo-print polo shirt'"},
        "category": {"type": "STRING", "enum": [c.value for c in ClothingCategory]},
        "sub_category": {"type": "STRING", "description": "Specific garment type, e.g. 'polo shirt', 'chinos', 'chelsea boots'"},
        "primary_color": {"type": "STRING", "enum": COLORS},
        "secondary_color": {"type": "STRING", "enum": COLORS + ["none"]},
        "pattern": {"type": "STRING", "description": "e.g. solid, striped, floral, camo, checked"},
        "seasons": {"type": "ARRAY", "items": {"type": "STRING", "enum": SEASONS}},
        "occasions": {"type": "ARRAY", "items": {"type": "STRING", "enum": OCCASIONS}},
    },
    "required": ["name", "category", "sub_category", "primary_color", "seasons", "occasions"],
}


def _as_jpeg(image_bytes: bytes, max_side: int = 1536) -> bytes:
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


async def create_showcase(image_bytes: bytes, client: Optional[GeminiClient] = None) -> bytes:
    """Returns PNG bytes of the white-background product shot."""
    client = client or gemini_client
    generated = await client.edit_image(_as_jpeg(image_bytes), "image/jpeg", SHOWCASE_PROMPT)
    # Normalise whatever format the model returned to an RGB PNG on white
    img = Image.open(io.BytesIO(generated))
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        img = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _clean_tags(raw: Dict[str, Any]) -> Dict[str, Any]:
    category = raw.get("category")
    if category not in {c.value for c in ClothingCategory}:
        category = None
    secondary = raw.get("secondary_color")
    seasons = [s for s in raw.get("seasons") or [] if s in SEASONS] or ["all_season"]
    pattern = (raw.get("pattern") or "").strip()
    sub_category = (raw.get("sub_category") or "").strip() or None
    if sub_category and pattern and pattern.lower() not in ("solid", "plain") and pattern.lower() not in sub_category.lower():
        sub_category = f"{pattern} {sub_category}"
    return {
        "name": (raw.get("name") or "").strip()[:150] or None,
        "category": category,
        "sub_category": sub_category[:100] if sub_category else None,
        "primary_color": raw.get("primary_color") if raw.get("primary_color") in COLORS else None,
        "secondary_color": secondary if secondary in COLORS else None,
        "seasons": seasons,
        "occasions": [o for o in raw.get("occasions") or [] if o in OCCASIONS],
    }


async def tag_garment(image_bytes: bytes, client: Optional[GeminiClient] = None) -> Dict[str, Any]:
    client = client or gemini_client
    raw = await client.generate_json(
        TAG_SYSTEM,
        TAG_PROMPT,
        TAG_SCHEMA,
        images=[(_as_jpeg(image_bytes, max_side=1024), "image/jpeg")],
        temperature=0.2,
    )
    return _clean_tags(raw)
