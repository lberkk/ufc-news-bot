"""UFC haber botu: RSS -> filtre -> Türkçe post -> X (veya drafts.md)."""
import sys
import time
from datetime import datetime

import yaml

from bot import feeds, images, publish, store, writer


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    db = store.Store()

    now = datetime.now(store.TZ)
    event = now.date().isoformat() in {str(d) for d in cfg.get("event_days") or []}
    if event:
        daily_limit = cfg.get("event_daily_limit", cfg["daily_limit"])
        max_per_run = cfg.get("event_max_per_run", cfg["max_per_run"])
        gap = 0
        print("Etkinlik günü: saat aralığı ve post arası süre uygulanmıyor.")
    else:
        daily_limit = cfg["daily_limit"]
        max_per_run = cfg["max_per_run"]
        gap = cfg.get("min_minutes_between_posts", 0) * 60
        start, end = cfg.get("active_hours", [0, 24])
        if not start <= now.hour < end:
            print(f"Aktif saatler dışında ({start}:00-{end}:00 TSİ), post atılmıyor.")
            return
        wait = gap - (time.time() - db.last_post_time())
        if wait > 0:
            print(f"Son posttan beri {gap // 60} dakika geçmedi, {int(wait // 60) + 1} dakika daha bekleniyor.")
            return

    fetched = feeds.fetch_all(cfg["feeds"])
    if not any(items for _, items in fetched):
        print("Hiçbir feed'den kayıt gelmedi.")
        sys.exit(1)

    cutoff = time.time() - cfg["max_age_hours"] * 3600
    # Tüm kaynaklar birlikte. Etkinlik gününde eskiden yeniye (sonuçlar sırasıyla),
    # normal günde yeniden eskiye (birikmiş haberlerde önce en güncel olan).
    candidates = sorted(
        (i for _, items in fetched for i in items if i["published"] >= cutoff),
        key=lambda i: i["published"],
        reverse=not event,
    )

    remaining = daily_limit - db.published_today()
    done = 0
    for item in candidates:
        if done >= max_per_run or remaining <= 0:
            break
        if done and gap:
            break  # normal günde koşu başına en fazla bir post (aralık kuralı)
        if db.seen(item["link"]):
            continue
        low = item["title"].lower()
        if any(k in low for k in cfg["exclude_keywords"]):
            db.record(item, "filtered")
            continue
        if db.similar(item["title"], cfg["similarity_window_hours"], cfg["similarity_threshold"]):
            db.record(item, "duplicate")
            continue
        item["body"] = feeds.fetch_article(item["link"])
        try:
            text, category = writer.write_post(item, cfg["llm"], db.recent_posts())
        except writer.LLMError as exc:
            print(f"[llm] {exc}")
            break  # kota bitti veya servis yok; haber sonraki çalıştırmada yeniden denenir
        if text is None:
            db.record(item, category or "skipped")
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
