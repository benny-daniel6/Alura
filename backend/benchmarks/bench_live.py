"""
Live end-to-end benchmark against a running Alura backend (the same API the phone uses).

1. Uploads every dataset photo WITHOUT a category hint and polls until processed:
   upload latency, time-to-ready, and auto-tag accuracy against the verified labels.
2. AI stylist evaluation across occasions x weather (a hot and a cold city):
   latency, rule validity (re-checked independently), completeness, layering in the cold,
   footwear coverage, variety, and anchor ("style this piece") compliance.
3. Read-endpoint latency (wardrobe list, outfits list).

Usage (backend running, from backend/):
  python benchmarks/bench_live.py --server http://127.0.0.1:8000 --email curator@aura-wardrobe.app
  python benchmarks/bench_live.py --skip-upload ...   # re-run the stylist part only
"""

import argparse
import json
import statistics
import time
from collections import Counter
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parents[2] / "data" / "benchmark"
OCCASIONS = ["casual_daily", "office_work", "evening_dinner", "athleisure"]
CITIES = {"hot": "Chennai", "cold": "Oslo"}
LIMITS = {"top": 1, "bottom": 1, "dress": 1, "one_piece": 1, "outerwear": 1, "footwear": 1,
          "headwear": 1, "bag": 1, "accessory": 2}


def pct(values, q):
    v = sorted(values)
    return round(v[min(len(v) - 1, int(round(q * (len(v) - 1))))], 3)


def check_outfit(cats):
    """Independent re-check of the wardrobe rules the server claims to enforce."""
    c = Counter(cats)
    problems = [f"{k} x{n}" for k, n in c.items() if n > LIMITS.get(k, 1)]
    one_piece = c["dress"] + c["one_piece"]
    if one_piece and (c["top"] or c["bottom"]):
        problems.append("one-piece mixed with separates")
    complete = bool(one_piece) or (c["top"] >= 1 and c["bottom"] >= 1)
    return problems, complete


def upload_all(client, manifest):
    rows = []
    for entry in manifest:
        path = DATA / entry["file"]
        t0 = time.perf_counter()
        r = client.post("/api/v1/wardrobe/items/upload",
                        files={"file": (path.name, path.read_bytes(), "image/jpeg")})
        r.raise_for_status()
        upload_s = time.perf_counter() - t0
        item_id = r.json()["item_id"]
        status, item = "pending", None
        while status in ("pending", "processing") and time.perf_counter() - t0 < 600:
            time.sleep(1.0)
            s = client.get(f"/api/v1/wardrobe/items/{item_id}/status").json()
            status, item = s["status"], s.get("item")
        ready_s = time.perf_counter() - t0
        row = {"file": entry["file"], "label": entry["category"], "label_color": entry["color"],
               "status": status, "upload_s": round(upload_s, 3), "ready_s": round(ready_s, 1),
               "pred_category": item and item["category"], "pred_color": item and item["primary_color"],
               "name": item and item["name"], "showcase": bool(item and item.get("showcase_image_url"))}
        rows.append(row)
        print(f"{entry['file']:32} {status:9} ready={ready_s:6.1f}s -> {row['pred_category']}/{row['pred_color']}", flush=True)
    done = [r for r in rows if r["status"] == "completed"]
    return {
        "uploaded": len(rows),
        "completed": len(done),
        "failed": len(rows) - len(done),
        "upload_request_p50_s": pct([r["upload_s"] for r in rows], 0.5),
        "time_to_ready_p50_s": pct([r["ready_s"] for r in done], 0.5) if done else None,
        "time_to_ready_p95_s": pct([r["ready_s"] for r in done], 0.95) if done else None,
        "auto_category_accuracy": round(sum(r["pred_category"] == r["label"] for r in done) / max(1, len(done)), 3),
        "category_errors": [f"{Path(r['file']).stem}: {r['label']} -> {r['pred_category']}"
                            for r in done if r["pred_category"] != r["label"]],
        "studio_photos": sum(r["showcase"] for r in done),
        "items": rows,
    }


def stylist_eval(client, items):
    by_id = {i["id"]: i for i in items}
    runs = []
    for weather, city in CITIES.items():
        for occasion in OCCASIONS:
            t0 = time.perf_counter()
            r = client.post("/api/v1/stylist/suggest", json={"occasion": occasion, "city": city, "num_outfits": 3},
                            timeout=120)
            dt = time.perf_counter() - t0
            r.raise_for_status()
            d = r.json()
            for o in d["outfits"]:
                cats = [by_id[i]["category"] for i in o["item_ids"] if i in by_id]
                problems, complete = check_outfit(cats)
                runs.append({"weather": weather, "city": city, "temp_c": d["weather"]["temperature_c"],
                             "occasion": occasion, "engine": d["engine"], "latency_s": round(dt, 3),
                             "name": o["name"], "items": [by_id[i]["name"] for i in o["item_ids"] if i in by_id],
                             "categories": cats, "problems": problems, "complete": complete,
                             "server_says_complete": o["is_complete"], "rationale": o["rationale"]})
    # Anchor compliance: "style this piece" for one item of each category present
    anchor_checks = []
    seen = set()
    for item in items:
        if item["category"] in seen:
            continue
        seen.add(item["category"])
        r = client.post("/api/v1/stylist/suggest",
                        json={"occasion": "casual_daily", "anchor_item_ids": [item["id"]], "num_outfits": 2}, timeout=120)
        r.raise_for_status()
        outs = r.json()["outfits"]
        anchor_checks.append({"anchor": item["name"], "category": item["category"], "looks": len(outs),
                              "all_include_anchor": all(item["id"] in o["item_ids"] for o in outs)})

    lat = [r["latency_s"] for r in runs]
    cold = [r for r in runs if r["weather"] == "cold"]
    hot = [r for r in runs if r["weather"] == "hot"]
    looks_per_request = Counter((r["city"], r["occasion"]) for r in runs)
    all_items_used = [n for r in runs for n in r["items"]]
    return {
        "requests": len(looks_per_request),
        "looks": len(runs),
        "engine": Counter(r["engine"] for r in runs),
        "latency_p50_s": pct(lat, 0.5),
        "latency_p95_s": pct(lat, 0.95),
        "rule_violations": sum(bool(r["problems"]) for r in runs),
        "complete_looks_pct": round(100 * sum(r["complete"] for r in runs) / len(runs), 1),
        "server_completeness_agrees_pct": round(100 * sum(r["complete"] == r["server_says_complete"] for r in runs) / len(runs), 1),
        "outerwear_in_cold_pct": round(100 * sum("outerwear" in r["categories"] for r in cold) / max(1, len(cold)), 1),
        "outerwear_in_hot_pct": round(100 * sum("outerwear" in r["categories"] for r in hot) / max(1, len(hot)), 1),
        "footwear_included_pct": round(100 * sum("footwear" in r["categories"] for r in runs) / len(runs), 1),
        "distinct_items_used": len(set(all_items_used)),
        "wardrobe_items": len(items),
        "most_reused_items": Counter(all_items_used).most_common(3),
        "anchor_compliance_pct": round(100 * sum(a["all_include_anchor"] for a in anchor_checks) / max(1, len(anchor_checks)), 1),
        "anchor_checks": anchor_checks,
        "weather_seen": {r["city"]: r["temp_c"] for r in runs},
        "looks_detail": runs,
    }


def read_latency(client, n=20):
    out = {}
    for name, path in [("wardrobe_list", "/api/v1/wardrobe/items"), ("outfits_list", "/api/v1/outfits")]:
        times = []
        for _ in range(n):
            t0 = time.perf_counter()
            client.get(path).raise_for_status()
            times.append(time.perf_counter() - t0)
        out[name] = {"p50_ms": round(pct(times, 0.5) * 1000, 1), "p95_ms": round(pct(times, 0.95) * 1000, 1)}
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default="curator@aura-wardrobe.app")
    parser.add_argument("--skip-upload", action="store_true")
    args = parser.parse_args()

    token = httpx.post(f"{args.server}/api/v1/auth/dev-token", params={"email": args.email}).json()
    token = token.get("access_token") or token.get("token")
    client = httpx.Client(base_url=args.server, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))

    result = {}
    if not args.skip_upload:
        result["upload"] = upload_all(client, manifest)
    items = [i for i in client.get("/api/v1/wardrobe/items").json() if i["status"] == "completed"]
    result["stylist"] = stylist_eval(client, items)
    result["read_latency"] = read_latency(client)

    out = DATA / "results"
    out.mkdir(exist_ok=True)
    name = "live_stylist.json" if args.skip_upload else "live.json"
    (out / name).write_text(json.dumps(result, indent=2, default=list), encoding="utf-8")
    summary = {k: {kk: vv for kk, vv in v.items() if kk not in ("items", "looks_detail", "anchor_checks")}
               for k, v in result.items()}
    print(json.dumps(summary, indent=2, default=list))


if __name__ == "__main__":
    main()
