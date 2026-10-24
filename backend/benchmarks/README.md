# Alura benchmarks

Measured 2026-10-24 on the development PC (Windows 11, CPU only, 16 GB RAM).

## Dataset

33 garment photos chosen to look like what a real user uploads: clothes on a bed, a hanger, a table, the floor, or held in a hand, shot on a phone. All come from Wikimedia Commons under CC0, public-domain, CC BY or CC BY-SA licences; `manifest.json` records each photo's author, licence and source page. Every label was checked by eye.

| top | bottom | outerwear | footwear | bag | headwear | accessory | dress |
|---|---|---|---|---|---|---|---|
| 6 | 8 | 5 | 6 | 3 | 2 | 3 | 0 (no usable free photos found) |

```
python benchmarks/build_dataset.py --collect --out ../data/benchmark   # candidates + contact sheets
# review, then list accepted ids + labels in benchmarks/dataset_labels.json
python benchmarks/build_dataset.py --finalize --out ../data/benchmark
```

## Background removal (`bench_pipeline.py`)

| Model | Median time / photo | Peak RAM | Visual review |
|---|---|---|---|
| **u2net (default)** | **0.5 s** | **~1.0 GB** | Good. Faded one pair of dark trousers on a white sheet. |
| isnet-general-use | 1.5 s | ~1.4 GB | Poor. Lost denim shorts and red chinos, and kept the white sheet instead of navy trousers. |
| birefnet-general | 23 s | ~8.4 GB | Best on cluttered backgrounds (e.g. a bedsheet), otherwise about equal to u2net. Needs a GPU. |

The "border leak" metric (how much of the photo's edge stays opaque) was too noisy to rank the models: garments that fill the frame touch the edge legitimately. The visual review on `results/cutouts_*.jpg` decided the ranking.

## Tagging and search (OpenCLIP ViT-B/32, used when Gemini is not configured)

| | Before | After |
|---|---|---|
| Category accuracy | 78.8% | **97.0%** |
| Colour accuracy | 63.6% | **72.7%** |
| Same-category nearest neighbour (similarity search) | 87.9% | 87.9% |
| CLIP time / photo | 1.86 s | **0.35 s** |

Changes:
- Several garment names per category, averaged over several prompt phrasings, instead of one comma-joined prompt. Hoodies and denim jackets used to be tagged "top" and scarves "bag".
- The text embeddings are cached instead of recomputed for every photo.
- Tags come from the cutout and the original photo together.
- Items are named by their specific garment type ("Black zip-up hoodie" rather than "Black outerwear").

These 33 photos also guided the prompt changes, so a larger held-out set is needed to confirm the gain.

## Live end to end (`bench_live.py`, real backend + Postgres + worker)

- **Uploads:** 33/33 processed, 0 failed. Upload request 49 ms (median); photo to ready ~2.1 s. Auto category accuracy 97%: black trousers were tagged as a jumpsuit.
- **Stylist (rule engine):** 8 requests, Chennai 27.6°C (drizzle) and Oslo 9.5°C, 4 occasions × 3 looks. Median latency 0.9 s.

| Stylist check | First run | After fixes |
|---|---|---|
| Garments used across 24 looks (of 35) | 12 | **30** |
| The same top in every look | yes (24/24) | no |
| Outerwear at 27.6°C | 100% | **0%** |
| Outerwear at 9.5°C | 100% | 100% |
| Rule violations / complete looks / anchor compliance | 0 / 100% / 100% | 0 / 100% / 100% |

Changes:
- The stylist knows each garment's formality and warmth from its type (blazer vs hoodie, loafers vs sneakers).
- Looks in one response don't reuse the same pieces.
- Restyle varies its results slightly.
- No heavy layers in the heat; shorts and sandals are avoided in the cold.

Known limitation: 1 of 3 Oslo athleisure looks still includes shorts, because the wardrobe has no warm sporty bottoms.

- **Read endpoints:** wardrobe list 10 ms and outfits list 9 ms (median), with 35 items.

```
python benchmarks/bench_pipeline.py --model u2net --clip
python benchmarks/bench_live.py --server http://127.0.0.1:8000 --email you@example.com
python benchmarks/bench_live.py --skip-upload ...   # stylist only
```
