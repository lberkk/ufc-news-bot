"""UFC haber botu: RSS -> filtre -> Türkçe post -> X (veya drafts.md)."""
import sys
import time

import yaml

from bot import feeds, images, publish, store, writer


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    db = store.Store()
    fetched = feeds.fetch_all(cfg["feeds"])
    if not any(items for _, items in fetched):
        print("Hiçbir feed'den kayıt gelmedi.")
        sys.exit(1)

    candidates = []
    cutoff = time.time() - cfg["max_age_hours"] * 3600
    for _, items in fetched:  # config sırası = öncelik
        candidates += sorted((i for i in items if i["published"] >= cutoff), key=lambda i: i["published"])

    remaining = cfg["daily_limit"] - db.published_last_24h()
    done = 0
    for item in candidates:
        if done >= cfg["max_per_run"] or remaining <= 0:
            break
        if db.seen(item["link"]):
            continue
        low = item["title"].lower()
        if any(k in low for k in cfg["exclude_keywords"]):
            db.record(item, "filtered")
            continue
        if db.similar(item["title"], cfg["similarity_window_hours"], cfg["similarity_threshold"]):
            db.record(item, "duplicate")
            continue
        try:
            text, category = writer.write_post(item, cfg["llm"])
        except writer.LLMError as exc:
            print(f"[llm] {exc}")
            break  # kota bitti veya servis yok; haber sonraki çalıştırmada yeniden denenir
        if text is None:
            db.record(item, "skipped")
            continue
        image, digest = images.prepare(item, cfg, db)
        post_id = publish.publish(text, image, item, category)
        db.record(item, "draft" if post_id == "draft" else "posted", text, digest, post_id)
        print(f"[ok] {post_id}: {text.splitlines()[0][:80]}")
        done += 1
        remaining -= 1
    print(f"Bitti: {done} post, günlük kalan hak {max(remaining, 0)}.")


if __name__ == "__main__":
    main()
