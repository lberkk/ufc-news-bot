"""Haberi LLM ile Türkçe posta çevirir. Sağlayıcılar sırayla denenir."""
import json
import os
import re

import requests

SYSTEM = """Bir UFC/MMA haber hesabı için Türkçe post yazıyorsun.
Sana İngilizce bir haberin başlığı ve özeti verilecek. Kurallar:
- Yalnızca verilen haberdeki bilgiyi kullan. Haberde olmayan hiçbir bilgi, tarih, sonuç veya yorum ekleme.
- Dövüşçü adlarını, etkinlik adlarını ve sayıları kaynaktaki gibi aynen koru.
- Kendi cümlelerinle yaz; başlığı kelimesi kelimesine çevirme.
- Sade haber dili kullan. Emoji, hashtag, link, ünlem ve soru cümlesi kullanma.
- Metin en fazla {limit} karakter olsun.
- Haber UFC/MMA ile ilgili değilse, bahis/izleme rehberi/reklam içeriğiyse veya haber değeri yoksa skip=true döndür.
Yalnızca şu JSON'u döndür:
{{"skip": false, "category": "Maç duyurusu|Sonuç|Sakatlık|Transfer|Açıklama|Diğer", "text": "..."}}"""


class LLMError(Exception):
    pass


def _call(provider, messages):
    key = os.environ.get(provider["key_env"], "")
    if not key:
        raise LLMError(f"{provider['key_env']} tanımlı değil")
    body = {"model": provider["model"], "messages": messages, "temperature": 0.3}
    if provider.get("reasoning_effort"):
        body["reasoning_effort"] = provider["reasoning_effort"]
    r = requests.post(
        provider["base_url"].rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60,
    )
    if r.status_code != 200:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]


def _parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise LLMError("JSON bulunamadı")
    return json.loads(m.group(0))


def write_post(item, cfg, call=_call):
    """(text, category) döner; haber atlanacaksa (None, None)."""
    suffix = f"\n\nKaynak: {item['source']}"
    limit = cfg["max_chars"] - len(suffix)
    messages = [
        {"role": "system", "content": SYSTEM.format(limit=limit)},
        {"role": "user", "content": f"Başlık: {item['title']}\nÖzet: {item['summary']}"},
    ]
    last = None
    for provider in cfg["providers"]:
        for attempt in range(2):
            try:
                data = _parse(call(provider, messages))
            except (LLMError, ValueError, KeyError, requests.RequestException) as exc:
                last = f"{provider['name']}: {exc}"
                print(f"[llm] {last}")
                break  # bu sağlayıcı çalışmıyor, sıradakine geç
            if data.get("skip"):
                return None, None
            text = (data.get("text") or "").strip()
            if text and len(text) <= limit and "http" not in text.lower():
                return text + suffix, data.get("category", "Diğer")
            last = f"{provider['name']}: geçersiz çıktı ({len(text)} karakter)"
            print(f"[llm] {last}")
            messages = messages[:2] + [
                {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                {"role": "user", "content": f"Metin {limit} karakteri aşıyor veya link içeriyor. Kısaltıp aynı JSON biçiminde yeniden yaz."},
            ]
    raise LLMError(f"Hiçbir sağlayıcı sonuç vermedi. Son hata: {last}")
