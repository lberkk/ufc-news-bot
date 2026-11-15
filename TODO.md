# Düzeltilecekler (15 Kasım 2026)

Durum: tetikleme cron-job.org üzerinden 15 dakikada bir çalışıyor. Prompt'taki zaman kipi
ve sıklet kuralları yayında. Aşağıdakiler açık.

## Öncelikli

1. **Sonuç ve canlı anlatım sayfaları post olarak atılıyor**
   - Örnekler: "UFC 334 Results: Gane vs. Hokit", "LIVE! UFC 334 Results: ...",
     "UFC 334 live blog: Bilal Hasan vs. Luis Gurule", "UFC 334: Live updates, highlights ...".
   - Bunlar haber değil, etkinlik öncesi açılan şablon sayfalar. Khamzat–Weidman hatası buradan çıktı.
   - Her biri bir gerçek sonuç haberinin sırasını ve bir günlük hakkı alıyor.
   - MMA Fighting ana kart maçları için iki ayrı kayıt giriyor: "live blog: A vs. B" ve "results: ...".
     Bot ikisini de paylaşıyor, aynı sonuç 15 dakika arayla iki kez çıkıyor (Hasan–Gurule, 15 Kasım 06:15 ve 06:30).
     Başlıklar farklı olduğu için benzerlik kontrolü yakalamıyor.
   - Karar: filtreyle elemek mi (`exclude_keywords`: `live blog`, `live updates`;
     `exclude_patterns`: `results: .+ vs\.? `), yoksa yalnızca prompt'a güvenmek mi.

2. **Etkinlik gecesi haberler birikiyor (`max_per_run: 1`)**
   - Site 15 dakikada birden fazla haber yayımlıyor, bot koşu başına 1 post atıyor.
   - MMA Fighting feed'i yalnızca son 10 haberi tutuyor; sırası gelmeyen haber feed'den düşüp kayboluyor.
   - Öneri: `max_per_run: 3`.

3. **Her maç sonucunun paylaşılması garanti değil**
   - Bot yalnızca ayrı haberi yazılan maçları görüyor.
   - Garantili yol: etkinlik sonuç sayfasını tekrar tekrar okuyup her biten maç için post atan ayrı bir özellik.
   - Önce dolu bir sonuç sayfasının biçimi incelenmeli (UFC 334 sayfası artık dolu, örnek olarak kullanılabilir).

4. **LLM hatası koşuyu yeşil bitiriyor**
   - Tüm sağlayıcılar hata verince bot `[llm] ...` yazıp çıkıyor, koşu başarılı görünüyor.
   - 14 Kasım 16:16 ve 16:30 koşuları bu yüzden sessizce post atmadı.
   - Öneri: bu durumda `sys.exit(1)`, böylece GitHub hata e-postası gelir.

5. **Tek LLM sağlayıcısı var (Groq, `openai/gpt-oss-120b`)**
   - Hız limitine takılırsa yedek yok.
   - Öneri: ikinci bir sağlayıcıyı listeye geri eklemek.

## Ayarlar

6. **`daily_limit: 40` geçici olarak yükseltildi**
   - Etkinlik bittikten sonra kalıcı bir değere çekilmeli.
   - X API'nin günlük post sınırı Developer Portal'dan doğrulanmalı (14 Kasım'da 24 saatte 20+ post kabul edildi).

7. **Sherdog haberleri geç işleniyor**
   - Adaylar feed sırasına göre diziliyor; MMA Fighting'de yeni haber oldukça Sherdog'a sıra gelmiyor.
   - Sherdog haberi 12 saatlik pencereyi (`max_age_hours`) doldurunca hiç paylaşılmadan düşüyor.
   - Seçenek: adayları feed'e göre değil, tümünü yayın saatine göre sıralamak.

8. **DRY_RUN modunda günlük limit çalışmıyor**
   - Taslaklar artık sayılmıyor; DRY_RUN açılırsa yalnızca koşu başına sınır kalıyor. Düşük öncelik.

## Elle yapılacaklar

9. **X'teki hatalı postu sil**: https://x.com/i/status/2121611808931021012
   (Khamzat–Weidman "karşı karşıya geldi"; ayrıca "hafif sıklet" yanlış, doğrusu "hafif ağır sıklet").

10. **Bildirimleri aç**
    - cron-job.org: "Notify me when execution fails".
    - GitHub: Settings → Notifications → Actions → yalnızca başarısız koşular.

11. **GitHub token'ının son kullanma tarihini takvime yaz**; süresi dolunca tetikleme `401` verir ve bot durur.

12. **UFC 334 sonrası kontrol**: hangi sonuç haberleri paylaşıldı, hangileri kaçtı (`state.db` ile feed karşılaştırması).
