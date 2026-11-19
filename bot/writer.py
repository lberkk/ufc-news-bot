"""Haberi LLM ile Türkçe posta çevirir. Sağlayıcılar sırayla denenir."""
import json
import os
import re

import anthropic
import requests

SYSTEM = """You write UFC/MMA news for two outlets: a short Turkish post for an X account, and a title and summary in Turkish and in English for a mobile news app.
You will receive the title and summary of an English news article. Rules for all texts:
- Write the Turkish texts in natural, fluent Turkish, in a plain news register.
- Use only information present in the article. Never add facts, dates, results or opinions that are not in it.
- Keep fighter names, event names and numbers exactly as written in the source.
- English headlines and previews describe upcoming fights in the present tense ("clash", "square off", "faces", "defends"). Treat a fight as already finished only if the article states its outcome (who won and how). Otherwise it has not happened yet: write it in the Turkish future tense ("karşılaşacak", "savunacak"), never in the past tense.
- Write your own sentences; do not translate the headline word for word.
- No emojis, hashtags, links, exclamation marks or questions.
- The post text must be at most {limit} characters.
- Use exactly these Turkish terms (English = Turkish):
{glossary}
- Keep these terms in English, exactly as written in the source: {keep}.
- Never replace a technique or finish name with a different one; use the name the article uses.
- Apart from the terms kept in English and proper names, do not leave English words in the text (write "efsane", not "legend"; "tecrübeli", not "veteran").
- Give judges' scores only together with who they favored; if unsure, state only the decision type.
- Set skip=true if the article is not about the UFC or UFC fighters (skip PFL, Bellator, ONE and other promotions unless a UFC fighter or the UFC itself is central to the story).
- You also receive the posts this account published recently. Set duplicate=true if the article adds no new fact to what those posts already say (the same result, announcement or statement told again, e.g. a highlights or video page for a fight whose result was already posted). If it does add new facts, the post text covers only what is new and does not repeat what was already posted.
- Reaction and opinion articles: statements by current or former UFC fighters named in the article count as new facts. Write who said what, naming them, and do not restate the result. Set skip=true if the reactions or opinions are those of journalists, the site's staff, analysts or fans (columns, analysis pieces, staff roundtables).
- title: a short, clear Turkish headline for the app, written in your own words.
- summary: a Turkish summary of the whole article for the app. Cover every relevant fact in the article, in as many sentences as it needs; there is no length limit. Separate paragraphs with a blank line. All rules above apply except the character limit.
- title_en, summary_en: the same title and summary in English for the app's English users, written in your own words; do not copy sentences from the article. The rules about facts, names, numbers, tense and judges' scores apply; the Turkish terms list and the rule against English words do not.
- fighters: the full names of the fighters the article mentions, exactly as written in the source.
- When skip or duplicate is true, leave text, title, summary, title_en and summary_en empty.

Examples of the expected post style:
- "Fighter A, UFC 400'de hafif sıklet kemeri için Fighter B ile karşılaşacak. Maç, 12 Aralık'taki etkinliğin ana karşılaşması olacak."
- "Fighter C, dizinden sakatlandığı için cumartesi günkü maçından çekildi. UFC, yerine geçecek isim için arayışta."

Return only this JSON:
{{"skip": false, "duplicate": false, "category": "Maç duyurusu|Sonuç|Sakatlık|Transfer|Açıklama|Diğer", "text": "...", "title": "...", "summary": "...", "title_en": "...", "summary_en": "...", "fighters": ["..."]}}"""


class LLMError(Exception):
    pass


def _call_anthropic(provider, messages):
    key = os.environ.get(provider["key_env"], "")
    if not key:
        raise LLMError(f"{provider['key_env']} tanımlı değil")
    client = anthropic.Anthropic(api_key=key, timeout=60.0, max_retries=1)
    try:
        r = client.messages.create(
            model=provider["model"],
            max_tokens=4000,
            system=messages[0]["content"],
            messages=messages[1:],
            output_config={"effort": "low"},
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
        raise LLMError(f"{type(exc).__name__}: {exc}") from exc
    if r.stop_reason == "refusal":
        raise LLMError("model yanıt vermeyi reddetti")
    return next((b.text for b in r.content if b.type == "text"), "")


def _call(provider, messages):
    if provider.get("type") == "anthropic":
        return _call_anthropic(provider, messages)
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
    return json.loads(m.group(0), strict=False)


def _app_fields(data):
    fields = {k: (data.get(k) or "").strip() for k in ("title", "summary", "title_en", "summary_en")}
    if not all(fields.values()) or "http" in " ".join(fields.values()).lower():
        return None
    fighters = [f.strip() for f in data.get("fighters") or [] if isinstance(f, str) and f.strip()]
    return {**fields, "fighters": fighters, "category": data.get("category") or "Diğer"}


def write_post(item, cfg, recent=(), call=_call):
    """Sonuç sözlüğü döner: {"status": "ok"|"skipped"|"duplicate", "text", "category", "title", "summary", "title_en", "summary_en", "fighters"}."""
    limit = cfg["max_chars"]
    glossary = "\n".join(f"  {en} = {tr}" for en, tr in cfg.get("glossary", {}).items())
    keep = ", ".join(cfg.get("keep_english", []))
    posted = "\n".join(f"- {p}" for p in recent) or "(none)"
    messages = [
        {"role": "system", "content": SYSTEM.format(limit=limit, glossary=glossary, keep=keep)},
        {"role": "user", "content": f"Recently published posts:\n{posted}\n\nTitle: {item['title']}\nSummary: {item['summary']}\nArticle text: {item.get('body', '')}"},
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
                return {"status": "skipped"}
            if data.get("duplicate"):
                return {"status": "duplicate"}
            app = _app_fields(data)
            text = (data.get("text") or "").strip()
            post_ok = text and len(text) <= limit and "http" not in text.lower()
            if app and post_ok:
                return {"status": "ok", "text": text, **app}
            if not app:
                last = f"{provider['name']}: başlık veya özet (TR/EN) eksik"
                fix = "A title or summary (Turkish or English) is missing or contains a link. Fill all of them and return the same JSON format."
            else:
                last = f"{provider['name']}: geçersiz post ({len(text)} karakter)"
                fix = f"The post text exceeds {limit} characters or contains a link. Shorten it and return the same JSON format."
            print(f"[llm] {last}")
            messages = messages[:2] + [
                {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
                {"role": "user", "content": fix},
            ]
    raise LLMError(f"Hiçbir sağlayıcı sonuç vermedi. Son hata: {last}")
