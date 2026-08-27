"""
Read-only API test harness for the distortion backend.
Lives OUTSIDE distortion-backend/. Talks to the running server over HTTP only.
"""
import sys
import json
import time
import urllib.parse
import urllib.request

BASE = "http://localhost:8002/api"

REQUIRED_PROFILE_FIELDS = [
    "distortion_index",
    "significance_inflation_rate",
    "anxiety_manufacturing_rate",
    "novelty_claim_rate",
    "loaded_language_rate",
    "temporal_distortion_rate",
    "consistency_score",
]

# (label, handle)
CASES = [
    ("RSS",        "simonw"),
    ("YouTube",    "lexfridman"),
    ("Bluesky",    "pfrazee.com"),
    ("Reddit",     "r/MachineLearning"),
    ("Weibo",      "weibo/2803301701"),
    ("Twitter/X",  "karaswisher"),
]


def http(method, path, timeout=600):
    url = BASE + path
    req = urllib.request.Request(url, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, body, time.time() - t0
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        return e.code, body, time.time() - t0
    except Exception as e:
        return None, f"{type(e).__name__}: {e}", time.time() - t0


def run_case(label, handle):
    print(f"\n{'='*70}\n[{label}]  handle = {handle}\n{'='*70}")
    enc = urllib.parse.quote(handle, safe="")

    # --- POST /api/analyze/{handle}
    status, body, dt = http("POST", f"/analyze/{enc}")
    print(f"POST /analyze/{handle}  ->  HTTP {status}  ({dt:.1f}s)")
    result = {"label": label, "handle": handle, "analyze_status": status,
              "ok": False, "errors": []}
    if status != 200:
        print(f"  ERROR body: {body[:1000]}")
        result["errors"].append(f"analyze HTTP {status}: {body[:500]}")
        return result

    try:
        data = json.loads(body)
    except Exception as e:
        result["errors"].append(f"analyze JSON parse failed: {e}")
        print(f"  ERROR: could not parse JSON: {body[:500]}")
        return result

    print("  --- FULL /analyze JSON ---")
    print("  " + json.dumps(data, ensure_ascii=False, indent=2).replace("\n", "\n  "))

    profile = data.get("profile", {})
    di = profile.get("distortion_index")
    if not isinstance(di, (int, float)):
        result["errors"].append(f"distortion_index is not a number: {di!r}")
    missing = [f for f in REQUIRED_PROFILE_FIELDS if f not in profile]
    if missing:
        result["errors"].append(f"missing profile fields: {missing}")
        print(f"  MISSING FIELDS: {missing}")
    else:
        print("  All 7 required profile fields present:")
        for f in REQUIRED_PROFILE_FIELDS:
            print(f"    {f:32s} = {profile[f]}")
    print(f"  total_posts_analyzed = {profile.get('total_posts_analyzed')}"
          f" | new_posts_crawled = {data.get('new_posts_crawled')}"
          f" | display_name = {data.get('account',{}).get('display_name')}")

    # --- GET /api/posts/{handle}  (verify >=1 post with content)
    status2, body2, dt2 = http("GET", f"/posts/{enc}?limit=5")
    print(f"GET  /posts/{handle}  ->  HTTP {status2}  ({dt2:.1f}s)")
    posts_with_content = 0
    sample = None
    if status2 == 200:
        try:
            pdata = json.loads(body2)
            posts = pdata.get("posts", [])
            posts_with_content = sum(1 for p in posts if (p.get("content") or "").strip())
            print(f"  posts total={pdata.get('total')}  returned={len(posts)}  with_content={posts_with_content}")
            for p in posts:
                if (p.get("content") or "").strip():
                    sample = p
                    break
            if sample:
                c = sample["content"].replace("\n", " ")
                print(f"  sample post [{sample.get('platform_id')}] "
                      f"types={sample.get('distortion_types')} "
                      f"method={sample.get('classification_method')}")
                print(f"    content: {c[:200]}")
        except Exception as e:
            result["errors"].append(f"posts JSON parse failed: {e}")
    else:
        result["errors"].append(f"posts HTTP {status2}: {body2[:300]}")
        print(f"  ERROR body: {body2[:500]}")

    if posts_with_content < 1:
        result["errors"].append("no posts with content")

    result["posts_with_content"] = posts_with_content
    result["ok"] = (not missing) and posts_with_content >= 1
    return result


def main():
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    results = []
    for label, handle in CASES:
        if only and label not in only and handle not in only:
            continue
        results.append(run_case(label, handle))

    print(f"\n\n{'#'*70}\nSUMMARY\n{'#'*70}")
    for r in results:
        state = "PASS" if r["ok"] else "FAIL"
        print(f"  [{state}] {r['label']:10s} {r['handle']:22s} "
              f"analyze=HTTP {r['analyze_status']} "
              f"posts_with_content={r.get('posts_with_content',0)}")
        for e in r["errors"]:
            print(f"          - {e}")


if __name__ == "__main__":
    main()
