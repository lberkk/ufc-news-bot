"""UFC haber botu: RSS -> filtre -> Türkçe haber -> Clinch uygulaması + X (veya drafts.md)."""
import sys
import time
from datetime import datetime

import yaml

from bot import clinch, feeds, images, publish, store, telegram, writer, xvideo


def process_new(cfg, db, fetched):
    """Yeni haberleri filtreler ve LLM ile yazar. Kabul edilenler X kuyruğuna girer."""
    cutoff = time.time() - cfg["max_age_hours"] * 3600
    # Tüm kaynaklar birlikte, eskiden yeniye: aynı haber iki kaynakta varsa önce yayımlanan kabul edilir.
    candidates = sorted(
        (i for _, items in fetched for i in items if i["published"] >= cutoff),
        key=lambda i: i["published"],
    )
    done = 0
    for item in candidates:
        if done >= cfg.get("max_process_per_run", 10):
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
        item["body"] = feeds.fetch_article(item["link"])
        try:
            result = writer.write_post(item, cfg["llm"], db.recent_posts())
        except writer.LLMError as exc:
            print(f"[llm] {exc}")
            return  # kota bitti veya servis yok; haber sonraki çalıştırmada yeniden denenir
        done += 1
        if result["status"] != "ok":
            db.record(item, result["status"])
            continue
        images.find_url(item)
        db.record(item, "queued", result)
        print(f"[yeni] {result['title'][:80]}")
        tg = cfg.get("telegram", {})
        if tg.get("enabled"):
            video = xvideo.find_video(item.get("html"), tg.get("only_video", True))
            if video and not db.video_used(video):
                db.set_video(item["link"], video)
                print(f"[xvideo] {video}")


def send_to_telegram(cfg, db):
    """Videolu haberlerin metnini ve alıntılanacak X linkini Telegram'a gönderir."""
    tg = cfg.get("telegram", {})
    if not tg.get("enabled"):
        return
    if not telegram.enabled():
        print("[telegram] TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID tanımlı değil, gönderilmiyor.")
        return
    sent = 0
    for row in db.tg_pending(tg.get("per_run", 5)):
        if not telegram.send(f"{row['post_text']}\n\n{row['video_url']}"):
            break  # kalanlar sonraki koşuda gönderilir
        db.set_tg_status(row["link"], "sent")
        sent += 1
    print(f"[telegram] {sent} videolu post gönderildi.")


def send_to_app(cfg, db):
    """Kabul edilen yeni haberleri uygulamaya gönderir."""
    if not clinch.enabled():
        print("[clinch] CLINCH_API_URL / CLINCH_API_KEY tanımlı değil, uygulamaya gönderilmiyor.")
        return
    sent = 0
    for row in db.app_pending(cfg.get("clinch", {}).get("send_per_run", 20)):
        status = clinch.send(row)
        if status is None:
            break  # sunucu hatası; kalanlar sonraki koşuda gönderilir
        db.set_app_status(row["link"], status)
        sent += status == "sent"
    print(f"[clinch] {sent} haber uygulamaya gönderildi.")


def post_to_x(cfg, db):
    """Kuyruktaki haberleri X kurallarına (saat, aralık, günlük limit) göre paylaşır."""
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
            print(f"[x] Aktif saatler dışında ({start}:00-{end}:00 TSİ), post atılmıyor.")
            return
        wait = gap - (time.time() - db.last_post_time())
        if wait > 0:
            print(f"[x] Son posttan beri {gap // 60} dakika geçmedi, {int(wait // 60) + 1} dakika daha bekleniyor.")
            return

    cutoff = time.time() - cfg["max_age_hours"] * 3600
    # Etkinlik gününde eskiden yeniye (sonuçlar sırasıyla), normal günde önce en güncel olan.
    queue = db.queued(cutoff, newest_first=not event)
    remaining = daily_limit - db.published_today()
    done = 0
    for item in queue:
        if done >= max_per_run or remaining <= 0 or (done and gap):
            break  # normal günde koşu başına en fazla bir post (aralık kuralı)
        image, digest = images.prepare(item, cfg, db)
        post_id = publish.publish(item["post_text"], image, item, item["category"])
        db.mark_posted(item["link"], "draft" if post_id == "draft" else "posted", digest, post_id)
        print(f"[x] {post_id}: {item['post_text'].splitlines()[0][:80]}")
        done += 1
        remaining -= 1
    print(f"[x] Bitti: {done} post, kuyrukta {len(queue) - done}, günlük kalan hak {max(remaining, 0)}.")


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    db = store.Store()
    fetched = feeds.fetch_all(cfg["feeds"])
    if not any(items for _, items in fetched):
        print("Hiçbir feed'den kayıt gelmedi.")
        sys.exit(1)
    process_new(cfg, db, fetched)
    send_to_app(cfg, db)
    send_to_telegram(cfg, db)
    post_to_x(cfg, db)


if __name__ == "__main__":
    main()
