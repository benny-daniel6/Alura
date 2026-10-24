import io
import logging
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image, ImageOps

from app.core.config import settings

logger = logging.getLogger(__name__)

# Zero-shot category vocabulary: several garment names per category, each embedded with a few
# photo-style templates and averaged (prompt ensembling). Single comma-joined prompts confused
# CLIP; e.g. hoodies and denim jackets were tagged "top" because they were missing from the list.
CATEGORY_NAMES = {
    "top": ["t-shirt", "shirt", "button-up shirt", "blouse", "polo shirt", "tank top", "crop top", "sweater"],
    "bottom": ["pants", "trousers", "jeans", "chinos", "shorts", "denim shorts", "skirt", "leggings"],
    "outerwear": ["jacket", "denim jacket", "leather jacket", "coat", "blazer", "hoodie", "zip-up hoodie",
                  "sweatshirt", "parka", "cardigan"],
    "dress": ["dress", "sundress", "gown", "maxi dress"],
    "footwear": ["shoes", "sneakers", "boots", "leather boots", "loafers", "high heels", "sandals"],
    "bag": ["handbag", "backpack", "tote bag", "shoulder bag", "clutch bag", "purse"],
    "accessory": ["belt", "leather belt", "scarf", "knitted scarf", "sunglasses", "wristwatch", "necklace", "necktie"],
    "headwear": ["baseball cap", "hat", "beanie", "bucket hat"],
    "one_piece": ["jumpsuit", "romper", "overalls"],
}
CATEGORY_TEMPLATES = ["a photo of a {}.", "a photo of a {} on a bed.", "a {} on a hanger.", "a {} laid flat."]
CATEGORIES = {k: ", ".join(v) for k, v in CATEGORY_NAMES.items()}  # human-readable summary

COLOR_CANDIDATES = [
    "black", "white", "grey", "navy blue", "beige", "brown",
    "olive green", "forest green", "sky blue", "red", "burgundy",
    "pink", "cream", "yellow", "purple", "orange"
]

SEASON_CANDIDATES = ["spring", "summer", "fall", "winter", "all_season"]


def clean_cutout_alpha(cutout_png: bytes, min_component_ratio: float = 0.05) -> bytes:
    """
    Drops small disconnected blobs (bits of bedding, a stray hand) from a cutout's alpha mask.
    Keeps every opaque region at least `min_component_ratio` the size of the largest one, so
    garments made of separate pieces (a pair of shoes) survive.
    """
    import numpy as np
    from scipy import ndimage

    img = Image.open(io.BytesIO(cutout_png)).convert("RGBA")
    rgba = np.array(img)
    alpha = rgba[:, :, 3]
    labels, count = ndimage.label(alpha > 127)
    if count <= 1:
        return cutout_png
    sizes = ndimage.sum(np.ones_like(labels), labels, index=range(1, count + 1))
    keep_ids = [i + 1 for i, size in enumerate(sizes) if size >= sizes.max() * min_component_ratio]
    keep = np.isin(labels, keep_ids)
    # Grow the kept region slightly so soft anti-aliased edges next to it are preserved
    keep = ndimage.binary_dilation(keep, iterations=3)
    rgba[:, :, 3] = np.where(keep, alpha, 0)
    out = io.BytesIO()
    Image.fromarray(rgba, "RGBA").save(out, format="PNG")
    return out.getvalue()


class MLPipeline:
    def __init__(self, rembg_model: Optional[str] = None):
        self.rembg_model = rembg_model or settings.REMBG_MODEL
        self.rembg_session = None
        self.clip_model = None
        self.clip_preprocess = None
        self.clip_tokenizer = None
        self._text_cache = None
        self._name_features: Dict[str, Any] = {}
        self.is_loaded = False

    def load_models(self):
        """
        Loads rembg session and OpenCLIP model ONCE at worker startup.
        """
        logger.info("Initializing ML pipeline models at worker startup...")

        # 1. Load rembg session
        try:
            import rembg
            self.rembg_session = rembg.new_session(self.rembg_model)
            logger.info(f"rembg session ({self.rembg_model}) loaded successfully.")
        except Exception as e:
            logger.warning(f"rembg not initialized: {e}. Fallback PIL processor will be used.")

        # 2. Load OpenCLIP model & tokenizer
        try:
            import open_clip
            import torch
            model, _, preprocess = open_clip.create_model_and_transforms(
                'ViT-B-32-quickgelu',
                pretrained='openai'
            )
            model.eval()
            self.clip_model = model
            self.clip_preprocess = preprocess
            self.clip_tokenizer = open_clip.get_tokenizer('ViT-B-32-quickgelu')
            logger.info("OpenCLIP ViT-B/32 loaded successfully.")
        except Exception as e:
            logger.warning(f"OpenCLIP not loaded: {e}. Fallback feature extractor will be used.")

        self.is_loaded = True

        missing = [name for name, obj in (("rembg", self.rembg_session), ("OpenCLIP", self.clip_model)) if obj is None]
        if missing and not settings.is_development:
            raise RuntimeError(
                f"ML models failed to load ({', '.join(missing)}). Heuristic fallbacks are only allowed in development."
            )

    def _text_features(self):
        """Category and colour text embeddings; computed once, they never change."""
        if self._text_cache is None:
            import torch

            def embed(prompts):
                with torch.no_grad():
                    f = self.clip_model.encode_text(self.clip_tokenizer(prompts))
                return f / f.norm(dim=-1, keepdim=True)

            cat_keys = list(CATEGORY_NAMES.keys())
            cat_rows = []
            self._name_features = {}
            for key in cat_keys:
                names = CATEGORY_NAMES[key]
                per_name = torch.stack([
                    (lambda f: f / f.norm())(embed([t.format(n) for t in CATEGORY_TEMPLATES]).mean(dim=0))
                    for n in names
                ])
                self._name_features[key] = per_name  # used to name the specific garment type
                f = per_name.mean(dim=0)
                cat_rows.append(f / f.norm())
            # A single plain template scored better for colour than an ensemble (70% vs 55% on the benchmark)
            colors = embed([f"clothing item in {c} color" for c in COLOR_CANDIDATES])
            self._text_cache = (cat_keys, torch.stack(cat_rows), colors)
        return self._text_cache

    def ensure_loaded(self):
        if not self.is_loaded:
            self.load_models()

    def _fallback_allowed(self, what: str, error: Optional[Exception] = None):
        if not settings.is_development:
            raise RuntimeError(f"{what} unavailable and fallbacks are disabled outside development") from error
        logger.warning(f"{what} unavailable; using development-only heuristic fallback.")

    def remove_background(self, image_bytes: bytes) -> bytes:
        """
        Removes background from image bytes using preloaded rembg session.
        Applies EXIF transpose first so smartphone orientation metadata is respected.
        Returns transparent RGBA PNG bytes.
        """
        raw_img = Image.open(io.BytesIO(image_bytes))
        transposed_img = ImageOps.exif_transpose(raw_img)

        transposed_buf = io.BytesIO()
        transposed_img.save(transposed_buf, format="PNG")
        normalized_bytes = transposed_buf.getvalue()

        if self.rembg_session is not None:
            try:
                import rembg
                return clean_cutout_alpha(rembg.remove(normalized_bytes, session=self.rembg_session))
            except Exception as e:
                logger.error(f"rembg removal failed: {e}")
                self._fallback_allowed("rembg background removal", e)
        else:
            self._fallback_allowed("rembg background removal")

        # Development-only fallback: ensure image is RGBA and generate clean transparent cutout
        img = transposed_img.convert("RGBA")
        out_buf = io.BytesIO()
        img.save(out_buf, format="PNG")
        return out_buf.getvalue()

    def generate_thumbnail(self, image_bytes: bytes, max_size: Tuple[int, int] = (256, 256)) -> bytes:
        raw_img = Image.open(io.BytesIO(image_bytes))
        img = ImageOps.exif_transpose(raw_img).convert("RGBA")
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        out_buf = io.BytesIO()
        img.save(out_buf, format="PNG", optimize=True)
        return out_buf.getvalue()

    def analyze_garment(self, cutout_bytes: bytes, original_bytes: Optional[bytes] = None) -> Dict[str, Any]:
        """
        Generates the 512-dim embedding (from the cutout, for similarity search) and predicts zero-shot
        category and colour. When the original photo is given, tags come from the cutout + photo
        embeddings combined: on the benchmark set that beat the cutout alone (97% vs 94% category,
        73% vs 70% colour), since a patchy cutout can hide the garment's shape.
        """
        raw_img = Image.open(io.BytesIO(cutout_bytes))
        img_transposed = ImageOps.exif_transpose(raw_img)

        # If OpenCLIP is available:
        if self.clip_model is not None and self.clip_preprocess is not None:
            try:
                import torch
                # Flatten the transparent cutout onto white so CLIP sees the garment, not hidden RGB noise
                rgba = img_transposed.convert("RGBA")
                img = Image.alpha_composite(Image.new("RGBA", rgba.size, (255, 255, 255, 255)), rgba).convert("RGB")
                image_input = self.clip_preprocess(img).unsqueeze(0)

                with torch.no_grad():
                    image_features = self.clip_model.encode_image(image_input)
                    image_features /= image_features.norm(dim=-1, keepdim=True)

                    tag_features = image_features
                    if original_bytes is not None:
                        original = ImageOps.exif_transpose(Image.open(io.BytesIO(original_bytes))).convert("RGB")
                        orig_features = self.clip_model.encode_image(self.clip_preprocess(original).unsqueeze(0))
                        orig_features /= orig_features.norm(dim=-1, keepdim=True)
                        tag_features = image_features + orig_features
                        tag_features /= tag_features.norm(dim=-1, keepdim=True)

                    cat_keys, cat_features, color_features = self._text_features()

                    # Zero-shot category and colour
                    best_cat_idx = (tag_features @ cat_features.T)[0].argmax().item()
                    predicted_category = cat_keys[best_cat_idx]
                    best_color_idx = (tag_features @ color_features.T)[0].argmax().item()
                    predicted_color = COLOR_CANDIDATES[best_color_idx]
                    # Specific garment type within the category, e.g. "hoodie" rather than "outerwear"
                    name_idx = (tag_features @ self._name_features[predicted_category].T)[0].argmax().item()
                    garment_type = CATEGORY_NAMES[predicted_category][name_idx]

                embedding_vector = image_features[0].cpu().tolist()

                return {
                    "category": predicted_category,
                    "sub_category": garment_type,
                    "primary_color": predicted_color,
                    "secondary_color": None,
                    "seasons": ["all_season"],
                    "embedding": embedding_vector,
                }
            except Exception as e:
                logger.error(f"OpenCLIP inference error: {e}")
                self._fallback_allowed("OpenCLIP analysis", e)
        else:
            self._fallback_allowed("OpenCLIP analysis")

        # Development-only fallback heuristic analysis:
        # Extracts dominant color from image pixels and returns synthetic 512-dim normalized vector
        img = Image.open(io.BytesIO(cutout_bytes)).convert("RGBA")
        dominant_color = self._extract_dominant_color(img)
        synthetic_embedding = [0.0] * 512
        synthetic_embedding[0] = 1.0  # Normalized unit vector

        return {
            "category": "top",
            "sub_category": f"{dominant_color} item",
            "primary_color": dominant_color,
            "secondary_color": None,
            "seasons": ["all_season"],
            "embedding": synthetic_embedding,
        }

    def _extract_dominant_color(self, img: Image.Image) -> str:
        small = img.resize((32, 32))
        pixels = [small.getpixel((x, y)) for x in range(32) for y in range(32)]
        visible_pixels = [p[:3] for p in pixels if len(p) < 4 or p[3] > 40]
        if not visible_pixels:
            return "black"

        avg_r = sum(p[0] for p in visible_pixels) // len(visible_pixels)
        avg_g = sum(p[1] for p in visible_pixels) // len(visible_pixels)
        avg_b = sum(p[2] for p in visible_pixels) // len(visible_pixels)

        if avg_r > 200 and avg_g > 200 and avg_b > 200:
            return "white"
        elif avg_r < 50 and avg_g < 50 and avg_b < 50:
            return "black"
        elif avg_b > avg_r + 20 and avg_b > avg_g:
            return "blue"
        elif avg_g > avg_r + 20 and avg_g > avg_b:
            return "green"
        elif avg_r > avg_g + 20 and avg_r > avg_b:
            return "red"
        elif abs(avg_r - avg_g) < 20 and avg_b < avg_r - 20:
            return "earth_tones"
        return "monochrome"


ml_pipeline = MLPipeline()
