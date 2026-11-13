"""Haberi LLM ile Türkçe posta çevirir. Sağlayıcılar sırayla denenir."""
import json
import os
import re

import requests

SYSTEM = """You write posts in Turkish for a UFC/MMA news account on X.
You will receive the title and summary of an English news article. Rules:
- Write the post in natural, fluent Turkish, in a plain news register.
- Use only information present in the article. Never add facts, dates, results or opinions that are not in it.
- Keep fighter names, event names and numbers exactly as written in the source.
- Write your own sentences; do not translate the headline word for word.
- No emojis, hashtags, links, exclamation marks or questions.
- The text must be at most {limit} characters.
- Use established Turkish MMA terms: "nakavt", "teknik nakavt", "hakem kararı", "bölünmüş karar", "sıklet", "kemer maçı", "ana kart". Keep technique names without a common Turkish equivalent in English (e.g. "rear-naked choke").
- Set skip=true if the article is not about UFC/MMA, is betting or how-to-watch content, is an advertisement, or has no news value.

Examples of the expected style:
- "Fighter A, UFC 400'de hafif sıklet kemeri için Fighter B ile karşılaşacak. Maç, 12 Aralık'taki etkinliğin ana karşılaşması olacak."
- "Fighter C, dizinden sakatlandığı için cumartesi günkü maçından çekildi. UFC, yerine geçecek isim için arayışta."

Return only this JSON:
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
    suffix = f"\n\n📰 {item['source']}"
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
                {"role": "user", "content": f"The text exceeds {limit} characters or contains a link. Shorten it and return the same JSON format."},
            ]
    raise LLMError(f"Hiçbir sağlayıcı sonuç vermedi. Son hata: {last}")
