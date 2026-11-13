"""Postu X'e gönderir; DRY_RUN açıkken drafts.md dosyasına yazar."""
import datetime
import os

DRAFTS = "drafts.md"
API = "https://api.x.com/2"


def dry_run():
    return os.environ.get("DRY_RUN", "true").lower() != "false"


def _session():
    from requests_oauthlib import OAuth1Session
    keys = [os.environ.get(k, "") for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
    if not all(keys):
        raise RuntimeError("X anahtarları eksik (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET)")
    return OAuth1Session(keys[0], keys[1], keys[2], keys[3])


def _upload(session, image):
    r = session.post(f"{API}/media/upload",
                     files={"media": ("image.jpg", image, "image/jpeg")},
                     data={"media_category": "tweet_image"}, timeout=60)
    if r.status_code >= 300:
        print(f"[x] görsel yüklenemedi (HTTP {r.status_code}): {r.text[:200]}")
        return None
    data = r.json().get("data", {})
    return data.get("id") or data.get("media_id_string")


def publish(text, image, item, category):
    """Post kimliğini döner; kuru çalıştırmada 'draft'."""
    if dry_run():
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(DRAFTS, "a", encoding="utf-8") as f:
            f.write(f"## {stamp} · {category} · {item['source']}\n\n{text}\n\n"
                    f"- Karakter: {len(text)}\n- Orijinal: {item['title']}\n- Haber: {item['link']}\n"
                    f"- Görsel: {item.get('image') if image else 'yok'}\n\n---\n\n")
        return "draft"
    session = _session()
    body = {"text": text}
    if image:
        media_id = _upload(session, image)
        if media_id:
            body["media"] = {"media_ids": [str(media_id)]}
    r = session.post(f"{API}/tweets", json=body, timeout=60)
    if r.status_code >= 300:
        raise RuntimeError(f"Post gönderilemedi (HTTP {r.status_code}): {r.text[:300]}")
    return r.json()["data"]["id"]
