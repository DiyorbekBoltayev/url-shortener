# URL Shortener — Biznes Logika va Funksiyalar

## Mundarija
- [Asosiy Biznes Funksiyalari](#asosiy-biznes-funksiyalari)
- [Analitika va Kuzatish](#analitika-va-kuzatish)
- [Biznes Modellari va Monetizatsiya](#biznes-modellari-va-monetizatsiya)
- [Foydalanuvchi Boshqaruvi](#foydalanuvchi-boshqaruvi)
- [Xavfsizlik va Muvofiqlik](#xavfsizlik-va-muvofiqlik)
- [Integratsiya Ekotizimi](#integratsiya-ekotizimi)
- [Nofunksional Talablar](#nofunksional-talablar)

---

## Asosiy Biznes Funksiyalari

### 1. URL Qisqartirish (Uzun URL → Qisqa URL)

**Mexanizm:** Uzun URLni qabul qilish, noyob qisqa kod yaratish (odatda 6-8 alfanumerik belgi), va xaritani saqlash. Qisqa URL tashrif buyurilganda, asl URLga HTTP 301/302 redirect bajarish.

| Platforma | Format | Eslatma |
|---|---|---|
| **Bit.ly** | `bit.ly/XXXXXX` (6-7 belgi) | Eng mashhur |
| **TinyURL** | `tinyurl.com/XXXXXXXX` (uzunroq) | Ba'zan o'qilishi oson |
| **Short.io** | Maxsus domenlar ta'kidlanadi | Brendlangan |
| **Rebrandly** | Maxsus domenlar asosiy format | Brend uchun mo'ljallangan |

**Barcha platformalar URLlarni normalizatsiya qiladi** — ortiqcha slashlar, protokol normalizatsiyasi, query parametr tartibi — dublikatlarni oldini olish uchun.

### 2. Maxsus Taxalluslar / Vanity URLlar

Foydalanuvchilar tasodifiy kod o'rniga maxsus orqa qism belgilashi mumkin:
- Misol: `bit.ly/mening-brendim-lansmanasi`

| Platforma | Mavjudligi |
|---|---|
| **Bit.ly** | Bepul tarifda mavjud (agar bo'sh bo'lsa), brendlangan linklar pullik |
| **Rebrandly** | Barcha tariflarda asosiy funksiya |
| **TinyURL** | Bepul tarifda maxsus taxalluslar |
| **Short.io** | Barcha tariflarda maxsus sluglar |

**Validatsiya qoidalari:** Odatda alfanumerik + defislar, minimum 3-4 belgi, so'kinish filtrlari, zahiralangan so'zlar ro'yxati.

### 3. Maxsus Domenlar (Brendlangan Qisqa Linklar)

Foydalanuvchilar platformaning standart domeni o'rniga o'z domenlarini olib keladi:
- Misol: `go.nike.com/sale` o'rniga `bit.ly/sale`

| Platforma | Narx | Domenlar soni |
|---|---|---|
| **Bit.ly** | ~$35/oy dan (Core tarif) | Enterprise da 10 tagacha |
| **Rebrandly** | Bepul tarifda 1 maxsus domen | Pullik tariflarda 5-100+ |
| **Short.io** | Bepul tarifda 1 domen (1000 linkgacha) | Pullik $19/oydan, 5 domen |
| **TinyURL** | $12.99/oydan | Pullik tariflarda |

**Texnik sozlash:** DNS CNAME yoki A yozuvi platformaning serverlariga yo'naltirilishi kerak. SSL sertifikatlari avtomatik ta'minlanadi (odatda Let's Encrypt orqali).

### 4. Link Muddati (TTL)

Linklar muayyan sana/vaqtdan keyin yoki ma'lum bosishlar sonidan keyin tugashi mumkin:

- **Bit.ly:** Faqat Enterprise tariflarda
- **Rebrandly:** Pullik tariflarda (Starter va undan yuqori)
- **Short.io:** Pullik tariflarda — sana va bosish asosida muddati tugashi

**Umumiy variantlar:** muayyan sana/vaqt, nisbiy vaqt (masalan, 7 kun), N bosishdan keyin, yoki kombinatsiya.

> Muddati tugaganda, platformalar odatda brendlangan "link muddati tugadi" sahifasini ko'rsatadi yoki sozlangan fallback URLga yo'naltiradi.

### 5. Parol bilan Himoyalangan Linklar

Tashrif buyuruvchilar yo'naltirilishdan oldin parol kiritishi kerak:

| Platforma | Qo'llab-quvvatlash |
|---|---|
| **Bit.ly** | Qo'llab-quvvatlamaydi |
| **Rebrandly** | Pullik tariflarda |
| **Short.io** | Team tarif va undan yuqori |
| **TinyURL** | Keng mavjud emas |

**Amalga oshirish:** Parol kiritishni talab qiluvchi oraliq sahifa ko'rsatiladi. Parol odatda xeshlanadi va link yozuvi yonida saqlanadi.

### 6. QR Kod Generatsiyasi

Har qanday qisqartirilgan link uchun avtomatik QR kod yaratish:

- **Bit.ly** — QR kodlar asosiy mahsulot liniyasi. Bepul tarifda oddiy QR kodlar, pullik tariflarda sozlanuvchi QR kodlar (ranglar, logotiplar, ramkalar)
- **Rebrandly** — Barcha tariflarda
- **Short.io** — Link yaratish bilan birga
- **TinyURL** — Bepul tarifda oddiy QR kodlar

**Ilg'or funksiyalar (pullik):** Maxsus ranglar, o'rnatilgan logotiplar, yumaloq burchaklar, ramka shablonlari, dinamik QR kodlar (maqsadni qayta bosmasdan o'zgartirish mumkin), SVG/PNG/PDF formatlarida yuklash, skanerlash kuzatish analitikasi.

### 7. Deep Linking (Mobil Ilova Yo'naltirish)

Foydalanuvchi mobilda ekanligini aniqlash va ilovaga (ilova do'koni yoki universal link orqali) yoki vebga yo'naltirish:

- **Bit.ly:** Enterprise tariflarda. Mobil o'lchov hamkorlari (MMP) bilan integratsiya
- **Rebrandly:** Qurilma/OS asosida shartli yo'naltirishlar (pullik)
- **Short.io:** Qurilma asosida yo'naltirish (pullik)

**Texnik:** Apple Universal Links / Android App Links yoki maxsus URI sxemalariga qaytish.

### 8. Link-in-Bio Sahifalari

Bitta landing sahifasida bir nechta linklar — asosan ijtimoiy tarmoq profillari uchun:

- **Bit.ly:** "Bitly Pages" — Linktree bilan raqobat qilish uchun
- **Rebrandly / Short.io:** Bunday mahsulot yo'q
- **Raqobatchilar:** Linktree (bozor yetakchisi), Later's Linkin.bio, Shorby

**Funksiyalar:** Sozlanuvchi mavzular/ranglar, profil rasmi, ijtimoiy tarmoq ikonkalari, link plitkalari, email/SMS to'plash, link ko'rinishini rejalashtirish.

---

## Analitika va Kuzatish

### 1. Bosish Kuzatish

- **Umumiy bosishlar:** Har bir redirect qayd etiladi. Barcha platformalar bepul tarifda ta'minlaydi
- **Noyob bosishlar:** IP manzil + user agent bo'yicha deduplikatsiya. Bit.ly pullik tariflarda ikkisini ham ko'rsatadi
- **Bosish tarixi:**
  - Bit.ly bepul: 30 kun
  - Bit.ly pullik: 2 yil (Core), cheksiz (Enterprise)
  - Rebrandly: 90 kun (bepul), 2 yil (pullik)
  - Short.io: 30 kun (bepul), 1 yil+ (pullik)

### 2. Geografik Ma'lumotlar

- **Mamlakat darajasi:** Ko'pchilik bepul tariflarda mavjud
- **Shahar darajasi:** Odatda pullik funksiya. Bit.ly Growth tarifda
- **Amalga oshirish:** IP-to-geolokatsiya qidirish MaxMind GeoIP2 bazalari yordamida. Redirect vaqtida bajariladi va click hodisasi bilan saqlanadi
- Xaritalar, jadvallar va diagrammalar shaklida ko'rsatiladi

### 3. Qurilma / Brauzer / OS Aniqlash

- **User-Agent tahlili:** Qurilma turi (mobil/planshet/desktop), brauzer (Chrome, Safari, Firefox), OS (iOS, Android, Windows)
- Ko'pchilik platformalarda pullik tariflarda mavjud
- Shartli yo'naltirishlar (qurilma maqsadlash) va analitika segmentatsiyasi uchun ishlatiladi

### 4. Referrer Kuzatish

- Bosishlar qayerdan kelganini kuzatish (masalan, Twitter, Facebook, email, to'g'ridan-to'g'ri)
- Redirect vaqtida **HTTP Referer headeri** olinadi
- **Cheklovlar:** Ko'p brauzerlar maxfiylik uchun Referer headerni o'chiradi yoki cheklaydi. To'g'ridan-to'g'ri/noma'lum trafik keng tarqalgan (ko'pincha bosishlarning 40-60%)

### 5. UTM Parametrlarini Boshqarish

- **UTM passthrough:** Qisqa URL manzil URLga qo'shilgan UTM parametrlarni saqlaydi
- **UTM builder:** Ba'zi platformalar link yaratishda ichki UTM teg yaratuvchisini taklif qiladi
- Kuzatiladigan UTM parametrlari: `utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`

| Platforma | UTM Builder |
|---|---|
| **Bit.ly** | Pullik tariflarda, kampaniya guruhlash Enterprise da |
| **Rebrandly** | UTM builder + izchil teglash uchun presetlar |
| **Short.io** | UTM parametrlar builder bilan |

### 6. Real-Time Analitika Dashboardlari

- **Bit.ly:** Deyarli real-time. Bosishdan bir necha daqiqa ichida ma'lumot mavjud
- **Short.io:** Pullik tariflarda real-time statistika
- **Rebrandly:** Pastroq tariflarda kechikish bilan, yuqori tariflarda deyarli real-time

**Umumiy dashboard elementlari:** chiziqli diagrammalar (vaqt bo'yicha bosishlar), geografik xaritalar, eng ko'p bosilgan linklar jadvali, referrer taqsimoti, qurilma/brauzer doira diagrammalari.

### 7. Analitika API

Barcha yirik platformalar analitikaga dasturiy kirish uchun REST API taqdim etadi:

- **Bit.ly:** `/v4/bitlinks/{bitlink}/clicks/summary`, mamlakat darajali, referrer ma'lumotlari
- **Rebrandly:** `/v2/links/{id}/count`, filtrlash bilan bosish endpointlari
- **Short.io:** `/api/links/statistics` turli o'lcham parametrlari bilan
- Raw bosish oqimi odatda faqat Enterprise

---

## Biznes Modellari va Monetizatsiya

### Narx Taqqoslash

#### Bit.ly

| Tarif | Narx | Linklar/oy | Maxsus Domen | Asosiy Funksiyalar |
|---|---|---|---|---|
| Bepul | $0 | 10 link, 5 QR | 0 | Oddiy qisqartirish, 30 kun analitika |
| Core | ~$35/oy | 100 link | 1 | Maxsus back-half, 30 kun analitika |
| Growth | ~$300/oy | 500 link | 3 | Shahar darajali, qurilma ma'lumotlari, UTM |
| Premium | ~$499/oy | 3,000 link | 10 | Brendlangan QR kodlar, ilg'or analitika |
| Enterprise | Maxsus | Cheksiz | 10+ | SSO/SAML, deep linking, raw data |

#### Rebrandly

| Tarif | Narx | Linklar | Maxsus Domen | Asosiy Funksiyalar |
|---|---|---|---|---|
| Bepul | $0 | 25 link | 1 | Oddiy qisqartirish, oddiy analitika |
| Essential | ~$13/oy | 500 link | 3 | Link teglar, UTM builder |
| Professional | ~$32/oy | 5,000 link | 5 | Maxsus skriptlar, link muddati |
| Enterprise | Maxsus | Cheksiz | Cheksiz | SSO, RBAC, ustuvor API |

#### Short.io

| Tarif | Narx | Linklar | Maxsus Domen | Asosiy Funksiyalar |
|---|---|---|---|---|
| Bepul | $0 | 1,000 link | 1 | Oddiy analitika, API kirish |
| Personal | ~$19/oy | 10,000 link | 5 | Batafsil statistika, parol himoyasi |
| Team | ~$49/oy | 50,000 link | 10+ | Jamoa hamkorligi, kampaniya kuzatish |
| Enterprise | Maxsus | Cheksiz | Cheksiz | SSO, SLA, maxsus qo'llab-quvvatlash |

#### TinyURL

| Tarif | Narx | Linklar | Asosiy Funksiyalar |
|---|---|---|---|
| Bepul | $0 | Cheksiz (analitikasiz) | Oddiy qisqartirish, maxsus taxalluslar |
| Pro | ~$12.99/oy | 5,000 kuzatiladigan | Analitika, maxsus domenlar |
| Bulk | ~$129/oy | 150,000 kuzatiladigan | Ilg'or analitika, API |

### Freemium Funksiya To'sish Namunasi

```
BEPUL TARIF:
├── Oddiy qisqartirish
├── Cheklangan link soni
├── Oddiy bosish hisoblari
├── Maxsus domen yo'q (yoki 1 ta qattiq cheklovlar bilan)
└── Cheklangan analitika tarixi

PULLIK TARIFLAR BOSQICHMA-BOSQICH OCHILADI:
├── Maxsus domenlar
├── Vanity URLlar
├── Ilg'or analitika (geo, qurilma, referrer)
├── Uzoqroq ma'lumot saqlash
├── Link boshqarish (teglar, papkalar, kampaniyalar)
├── QR kod sozlash
├── Ommaviy operatsiyalar
├── Jamoa funksiyalari
└── Yuqori rate limitli API kirish

ENTERPRISE GA CHEKLANGAN:
├── SSO/SAML
├── SLA kafolatlari
├── Maxsus qo'llab-quvvatlash
├── Raw data eksport
├── Deep linking
└── Cheksiz hamma narsa
```

### Daromad Modeli

- **Asosiy:** SaaS obunalar (oylik/yillik)
- **Ikkilamchi:** Enterprise shartnomalar, ortiqcha to'lovlar, API foydalanishga asoslangan hisob-kitob

---

## Foydalanuvchi Boshqaruvi

### Ish Fazo / Tashkilotlar

- **Bit.ly:** "Tashkilot" ichida "Guruhlar". Enterprise akkauntlarida bir nechta guruhlar
- **Rebrandly:** "Ish fazolari" modeli. Har bir ish fazosida o'z linklari, domenlari, jamoa a'zolari
- **Short.io:** Birgalikda link boshqarish bilan jamoa ish fazolari

**Umumiy naqsh:** Tashkilot bir yoki bir nechta ish fazo/guruhlarni o'z ichiga oladi. Har birida o'z linklari, domenlari va analitikasi.

### Jamoa Hamkorligi

- Ish fazosida birgalikda link kutubxonalari
- Link egaligi va jamoa a'zolari o'rtasida uzatish
- Kim link yaratgan/o'zgartirganini ko'rsatuvchi faoliyat jurnallari
- Jamoa bo'ylab birgalikda maxsus domenlar
- Ommaviy link boshqarish (teglash, arxivlash, o'chirish)

### Rol Asosida Kirish Nazorati (RBAC)

| Rol | Huquqlar |
|---|---|
| **Egasi/Admin** | To'liq kirish. To'lov, domenlar, jamoa a'zolari, sozlamalarni boshqarish |
| **Menejer** | Linklar yaratish/tahrirlash/o'chirish, barcha analitikani ko'rish, teglar boshqarish. To'lov yoki domenlarni boshqara olmaydi |
| **A'zo** | Linklar yaratish, o'z analitikasini ko'rish. Boshqalarning linklarini o'chira olmaydi |
| **Ko'ruvchi** | Faqat linklar va analitikani ko'rish. Yaratish yoki o'zgartirish mumkin emas |

### SSO / SAML Integratsiya

- Barcha yirik platformalarda faqat Enterprise funksiya
- **Bit.ly:** SAML 2.0 SSO. Okta, Azure AD, OneLogin qo'llab-quvvatlaydi
- **Amalga oshirish:** SP-boshlangan SAML oqimi. SCIM provisioning avtomatlashtirilgan foydalanuvchi hayot tsikli boshqaruvi uchun

### API Kalit Boshqaruvi

- Barcha platformalar API kalit/OAuth token generatsiyasini ta'minlaydi
- **Bit.ly:** OAuth 2.0 tokenlar. Rate limitlar tarifga qarab (bepul: ~100 so'rov/soat, pullik: 1,000-5,000+/soat)
- **Rebrandly:** Scopelar bilan API kalitlar. Pullik tariflarda akkaunt boshiga bir nechta kalit
- **Short.io:** Domen darajasidagi ruxsatlar bilan API kalitlar

---

## Xavfsizlik va Muvofiqlik

### 1. Spam/Zararli Dastur Link Aniqlash

Barcha yirik platformalar manzil URLlarni tahdid razvedka bazalariga qarshi tekshiradi:

- **Bit.ly:** Google Safe Browsing API va ichki bazalar ishlatadi. Belgilangan linklar ogohlantirish oraliq sahifasini ko'rsatadi
- **Amalga oshirish:**
  - Google Safe Browsing, PhishTank, VirusTotal va maxsus bloklist bilan tekshirish
  - Link yaratish vaqtida skanerlash
  - Mavjud linklarni davriy qayta skanerlash
  - Foydalanuvchilarga zararli linklarni xabar qilish imkoniyati

### 2. GDPR Muvofiqlik

- **Ma'lumotlarni saqlash:** Bosish va foydalanuvchi ma'lumotlari qancha vaqt saqlanishi uchun aniq siyosatlar
- **Ma'lumot eksporti va o'chirish:** Foydalanuvchi so'rovi bo'yicha
- **IP anonimlashtirish:** Ba'zi platformalar analitikada PII saqlashdan qochish uchun IP xeshlash/anonimlashtirish taklif qiladi
- **Cookie rozilik:** Cookie ishlatuvchi platformalar ePrivacy/cookie qonunlariga rioya qilishi kerak
- **Ma'lumotlar joylashuvi:** Enterprise tariflarda ma'lumot joylashuvi variantlari (EU, US)
- **Asosiy talablar:** Maxfiylik siyosati, DSAR boshqarish, o'chirish huquqi, ma'lumot ko'chirish, buzilish haqida xabar berish

### 3. Link Suiiste'molini Oldini Olish

- Link yaratishda rate limiting (bepul: 10-50 link/kun, pullik: yuqori limitlar)
- Ochiq link yaratish formalarida CAPTCHA yoki bot aniqlash
- Link fermalari, spam naqshlari, fishing urinishlarini avtomatik aniqlash
- Belgilangan linklar uchun qo'lda ko'rib chiqish navbatlari
- Suiiste'mol xabar berish mexanizmlari
- Domen obro'sini monitoring qilish

### 4. Rate Limiting

| Platforma | Bepul Tarif | Pullik Tarif | Enterprise |
|---|---|---|---|
| **Bit.ly** | ~100 API chaqiruv/soat | 1,000-5,000+/soat | Maxsus limitlar |
| **Rebrandly** | 10 so'rov/sekund | 150+ so'rov/sekund gacha | Maxsus |
| **Short.io** | Tarif asosida | Tarif asosida | Maxsus |

**Amalga oshirish:** Token bucket yoki sliding window. HTTP 429 (Too Many Requests) `Retry-After` headeri bilan qaytarish. Rate limit headerlari: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

### 5. Bot Aniqlash

Aniq analitika uchun inson bosishlarini bot/crawler trafikidan ajratish:

- **User-agent filtrlash** (ma'lum bot UA: Googlebot, Bingbot, Slackbot)
- Shubhali trafik uchun JavaScript challenge sahifalari
- Bosish tezligi tahlili
- IP obro' baholash
- **Bit.ly** ma'lum botlarni bosish hisoblaridan filtrlaydi

> Bu analitika aniqligi uchun muhim — bot trafik barcha redirectlarning 30-60% ni tashkil qilishi mumkin.

---

## Integratsiya Ekotizimi

### REST API

Barcha yirik platformalar keng qamrovli REST APIlarni taklif qiladi:

**Umumiy endpointlar:**
```
POST   /api/v1/links          Qisqa link yaratish
GET    /api/v1/links          Barcha linklarni ko'rish (pagination bilan)
GET    /api/v1/links/{id}     Muayyan link tafsilotlari
PATCH  /api/v1/links/{id}     Linkni yangilash
DELETE /api/v1/links/{id}     Linkni o'chirish
GET    /api/v1/links/{id}/clicks  Bosish analitikasi

GET    /{code}                Redirect endpoint (ochiq, /api ostida emas)
```

**Odatiy yaratish so'rovi:**
```json
POST /api/v1/links
{
  "url": "https://example.com/juda/uzun/url",
  "customSlug": "mening-linkim",
  "domain": "qisqa.uz",
  "expiresAt": "2026-12-31",
  "maxVisits": 1000,
  "password": "maxfiy",
  "tags": ["marketing", "q1"],
  "title": "Mening Kampaniya Linkim"
}
```

**Odatiy javob:**
```json
{
  "id": "clx123abc",
  "shortUrl": "https://qisqa.uz/mening-linkim",
  "shortCode": "mening-linkim",
  "longUrl": "https://example.com/juda/uzun/url",
  "createdAt": "2026-04-06T12:00:00Z",
  "clicks": 0,
  "domain": "qisqa.uz",
  "tags": ["marketing", "q1"]
}
```

### Webhooklar

- **Odatiy hodisalar:** `link.created`, `link.updated`, `link.deleted`, `click.recorded`
- Foydalanuvchi sozlagan endpointga JSON payload bilan HTTP POST
- Eksponensial backoff bilan qayta urinish logikasi
- Xavfsizlik uchun HMAC imzo tekshirish

### Zapier / Make Integratsiyalari

- **Bit.ly:** Rasmiy Zapier integratsiyasi. 3,000+ ulangan ilova
- Umumiy foydalanish holatlari:
  - Google Sheets dan URLlarni avtomatik qisqartirish
  - Qisqartirilgan linklarni Slack ga joylash
  - Forma yuborishlaridan link yaratish
  - Bosish ma'lumotlarini CRM larga sinxronlash

### Ijtimoiy Tarmoq Integratsiyalari

- **Bit.ly:** Hootsuite, Sprout Social, Buffer bilan to'g'ridan-to'g'ri integratsiya
- Open Graph / Twitter Card metadata: Qisqa URL ijtimoiy tarmoqlarda bo'lishilganda ko'rinadigan link oldindan ko'rishni (sarlavha, tavsif, rasm) sozlash

---

## Nofunksional Talablar

### Past Kechikishli Redirectlar

- **Maqsad:** Redirect javobi uchun **< 100ms** (HTTP 301/302)
- **Bit.ly:** Global miqyosda odatda 50-100ms ichida yakunlanadi
- **Amalga oshirish strategiyalari:**
  - Issiq linklar uchun in-memory keshlash (Redis/Memcached)
  - Global CDN / edge tarmoq (Cloudflare, Fastly, AWS CloudFront)
  - Faqat kesh misslar uchun baza o'qishlari
  - Redirect vaqtida minimal ishlov: qisqa kodni qidirish, bosishni asinxron qayd etish, 301/302 qaytarish
  - Bosish qayd etish asinxron bo'lishi kerak (Kafka/SQS message queue)

### Yuqori Mavjudlik

- **Maqsad:** Minimum 99.9% uptime, Enterprise SLA uchun 99.99%
- **Amalga oshirish:**
  - Ko'p mintaqali / ko'p AZ joylashtirish
  - Ma'lumotlar bazasi replikatsiyasi
  - Health checklar va avtomatik failover
  - **Graceful degradation:** Analitika pipeline ishlamasa ham, redirectlar ishlashda davom etishi kerak
  - Downstream bog'liqliklar uchun circuit breakerlar

### Ma'lumotlarni Saqlash Siyosatlari

| Ma'lumot turi | Bepul | Pullik | Enterprise |
|---|---|---|---|
| **Bosish ma'lumotlari** | 30 kun | 90 kun - 2 yil | Cheksiz |
| **Link ma'lumotlari** | Cheksiz (o'chirilmasa) | Cheksiz | Cheksiz |
| **Audit jurnallari** | - | - | 1-2 yil |

### Masshtablanish Talablari

- **Link yaratish:** Bursty link yaratishni boshqarish kerak (marketing kampaniyalari, viral hodisalar)
- **Redirect trafik:** Read-heavy ish yuki. Read:Write nisbati 100:1 dan 1000:1 gacha
- **Analitika qabul qilish:** Yuqori o'tkazuvchanlik bilan bosish hodisalarini qabul qilish. Kafka bilan event streaming + Spark/Flink bilan batch ishlov

### Saqlash Hisoblari

```
Har bir link yozuvi: ~500 bayt
1 milliard link = ~500 GB

Har bir bosish hodisasi: ~200 bayt  
10 milliard bosish/oy = ~2 TB/oy raw bosish ma'lumotlari
```
