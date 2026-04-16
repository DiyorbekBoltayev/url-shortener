# URL Shortener — Ochiq Kodli Yechimlar va Texnologiya Steklari

## Mundarija
- [Mashhur Ochiq Kodli URL Shortenerlar](#mashhur-ochiq-kodli-url-shortenerlar)
- [Texnologiya Stek Tanlovlari](#texnologiya-stek-tanlovlari)
- [API Dizayn Naqshlari](#api-dizayn-naqshlari)
- [Arxitekturaviy Yondashuvlar Taqqoslashi](#arxitekturaviy-yondashuvlar-taqqoslashi)
- [Ishlash Ko'rsatkichlari](#ishlash-korsatkichlari)

---

## Mashhur Ochiq Kodli URL Shortenerlar

### 1. Dub.co (avval dub.sh)

| Xususiyat | Tafsilot |
|---|---|
| **GitHub** | `github.com/dubinc/dub` |
| **Yulduzlar** | ~19,000+ (tezda o'smoqda) |
| **Faollik** | Juda faol; YC qo'llab-quvvatlovchi startap, muntazam relizlar |
| **Texnologiya Stek** | Next.js 14 (App Router), TypeScript, Tailwind CSS, Prisma ORM, PlanetScale (MySQL), Upstash Redis, Tinybird (analitika), Vercel (joylashtirish) |
| **Litsenziya** | AGPL-3.0 |
| **Asosiy Funksiyalar** | Zamonaviy UI, link analitika, maxsus domenlar, jamoa ish fazolari, teglar, UTM builder, QR kod, API/OAuth, webhooklar, link muddati, parol himoyasi, OG rasm sozlash, Vercel edge redirectlar |
| **O'z-o'zini joylashtirish** | **Juda qiyin** — PlanetScale, Upstash Redis, Tinybird, Vercel va boshqa ~8 ta bulut xizmatiga bog'liq |
| **Afzalliklari** | Eng zamonaviy va chiroyli UI/UX, juda ko'p funksiyali, ajoyib DX, TypeScript, ajoyib API/SDK, faol kompaniya |
| **Kamchiliklari** | O'z-o'zini joylashtirish juda qiyin, AGPL litsenziyasi cheklovchi, murakkab infratuzilma, bulut xarajatlari yuqori |

### 2. YOURLS (Your Own URL Shortener)

| Xususiyat | Tafsilot |
|---|---|
| **GitHub** | `github.com/YOURLS/YOURLS` |
| **Yulduzlar** | ~10,700 |
| **Faollik** | Yetuk/qo'llab-quvvatlash rejimi; vaqti-vaqti bilan relizlar, faol plugin ekotizimi |
| **Texnologiya Stek** | PHP (vanilla, framework yo'q), MySQL/MariaDB |
| **Litsenziya** | MIT |
| **Asosiy Funksiyalar** | Bookmarkletlar, maxsus qisqa URLlar, keng plugin API (~200+ jamoat plaginlari), referrer/geo bilan bosish statistikasi, shaxsiy yoki ochiq sozlash, JSON/XML API, parol himoyalangan linklar |
| **O'z-o'zini joylashtirish** | PHP 7.4+, MySQL 5.0+ yoki MariaDB, Apache/Nginx mod_rewrite bilan |
| **Afzalliklari** | Juda yetuk (2009 dan), katta plugin ekotizimi, har qanday shared hostingda osongina joylashtirish, juda yengil, yaxshi hujjatlashtirilgan |
| **Kamchiliklari** | Ichki kesh qatlami yo'q, vanilla PHP (zamonaviy framework yo'q), yangi vositalar bilan solishtirganda cheklangan analitika, UI eskirgan, ichki Docker qo'llab-quvvatlash yo'q, jamoa/ko'p foydalanuvchi boshqaruvi yo'q |

### 3. Kutt.it

| Xususiyat | Tafsilot |
|---|---|
| **GitHub** | `github.com/thedevs-network/kutt` |
| **Yulduzlar** | ~8,400 |
| **Faollik** | O'rtacha; vaqti-vaqti bilan yangilanishlar, jamoat tomonidan boshqariladi |
| **Texnologiya Stek** | Node.js (Express.js), TypeScript, PostgreSQL, Redis, Next.js (frontend) |
| **Litsenziya** | MIT |
| **Asosiy Funksiyalar** | Maxsus domenlar, link muddati, parol himoyalangan linklar, API kalit autentifikatsiyasi bilan API, bosish statistikasi (brauzer, OS, mamlakat), admin panel, domen darajasida boshqarish |
| **O'z-o'zini joylashtirish** | Node.js 12+, PostgreSQL, Redis, Docker qo'llab-quvvatlash |
| **Afzalliklari** | Zamonaviy JavaScript stek, toza UI, maxsus domen, yaxshi API, ichki Redis kesh, Docker qo'llab-quvvatlash |
| **Kamchiliklari** | Ishlab chiqish sezilarli sekinlashgan, ba'zi ochiq muammolar uzoq vaqt hal qilinmagan, hujjatlashtirish yaxshilanishi mumkin, cheklangan plugin/kengaytma tizimi |

### 4. Shlink

| Xususiyat | Tafsilot |
|---|---|
| **GitHub** | `github.com/shlinkio/shlink` |
| **Yulduzlar** | ~3,200 |
| **Faollik** | Juda faol; maxsus dasturchi tomonidan muntazam relizlar |
| **Texnologiya Stek** | PHP 8.2+ (Mezzio framework, Doctrine ORM); MySQL, MariaDB, PostgreSQL, SQLite, MS SQL Server qo'llab-quvvatlaydi; ixtiyoriy Redis/Mercure |
| **Litsenziya** | MIT |
| **Asosiy Funksiyalar** | REST API-birinchi dizayn, ko'p domen qo'llab-quvvatlash, QR kod yaratish, GeoLite2 IP geolokatsiya, teg asosida tashkil etish, bot/crawler aniqlash, tashriflash chegaralash, link muddati, Mercure/RabbitMQ real-time hodisa integratsiyasi, yetim tashriflash kuzatish, alohida web klient (`shlink-web-client`) |
| **O'z-o'zini joylashtirish** | PHP 8.2+, har qanday qo'llab-quvvatlanadigan RDBMS, Docker rasmiy (tavsiya) |
| **Afzalliklari** | Eng ko'p funksiyali PHP yechimi, ajoyib API dizayni (OpenAPI hujjatlashtirilgan), bir nechta bazani qo'llab-quvvatlash, juda faol ishlab chiqish, birinchi darajali Docker, real-time hodisalar, ajoyib hujjatlashtirish |
| **Kamchiliklari** | YOURLS dan kichikroq jamoa, ichki UI yo'q (alohida web-client kerak), YOURLS dan sozlash murakkabroq |

### 5. Polr

| Xususiyat | Tafsilot |
|---|---|
| **GitHub** | `github.com/cydrobolt/polr` |
| **Yulduzlar** | ~5,000 |
| **Faollik** | **Amalda to'xtatilgan** ~2020 dan beri; Polr 2.x oxirgi asosiy versiya |
| **Texnologiya Stek** | PHP (Laravel 5.x), MySQL/MariaDB/PostgreSQL/SQLite |
| **Litsenziya** | GPL-2.0 |
| **Afzalliklari** | Toza Laravel kodlar bazasi, yaxshi UI, oson sozlash |
| **Kamchiliklari** | **Tashlab qo'yilgan**, eski Laravel 5.x da qolib ketgan, yangilanishlar yo'qligi sababli xavfsizlik muammolari, Docker yo'q |

> **Tavsiya:** Polr dan foydalanmang — faol ishlab chiqilmayapti.

### 6. Boshqa E'tiborli Ochiq Kodli Yechimlar

| Loyiha | Stek | Yulduzlar | Eslatma |
|---|---|---|---|
| **Sink** | Cloudflare Workers, Nuxt, Cloudflare KV | ~2,500+ | Edge-native URL shortener, Cloudflare uchun mo'ljallangan |
| **Reduced.to** | NestJS, Angular/Qwik, Redis, PostgreSQL | ~1,500+ | Zamonaviy monorepo |
| **Chhoto-URL** | Rust (Actix-web), SQLite | ~500+ | Minimal/yengil, o'smoqda |
| **Lstu** | Perl (Mojolicious), SQLite/PostgreSQL | ~200 | Niche, lekin yengil |
| **UrlHum** | PHP (Laravel), MySQL | ~700 | Analitikaga yo'naltirilgan |

---

## Texnologiya Stek Tanlovlari

### Tillar va Frameworklar

| Til | Ishlatuvchi Loyihalar | Eslatmalar |
|---|---|---|
| **PHP** | YOURLS, Shlink, Polr, UrlHum | Tarixan eng keng tarqalgan; Shlink Mezzio + Doctrine bilan eng zamonaviy PHP |
| **TypeScript/Node.js** | Kutt, Dub.co, Reduced.to, Sink | Tezda o'smoqda; Dub Next.js, Kutt Express, Reduced.to NestJS |
| **Go** | Turli kichik loyihalar (gosh, go-url-shortener) | Past kechikish tufayli yuqori samaradorlik redirect xizmatlari uchun ajoyib |
| **Rust** | Chhoto-URL, maxsus amalga oshirishlar | Samaradorlikka muhim redirect xizmatlari uchun o'sib borayotgan tanlov; Actix-web keng tarqalgan |
| **Python** | Turli (Django/Flask asosli) | Ishlab chiqarish URL shortenerlar uchun kamroq tarqalgan; ko'proq darsliqlarda |
| **Java** | Enterprise maxsus amalga oshirishlar | Kamdan-kam ochiq manba, lekin enterprise da keng (Spring Boot) |

### Ma'lumotlar Bazalari

| Ma'lumotlar Bazasi | Ishlatuvchi | Foydalanish holati |
|---|---|---|
| **MySQL/MariaDB** | YOURLS, Polr, Dub.co (PlanetScale), Shlink | Eng keng tarqalgan tanlov |
| **PostgreSQL** | Kutt, Shlink, Reduced.to | Node.js ekotizimida afzal; yaxshiroq JSON qo'llab-quvvatlash |
| **SQLite** | Polr, Shlink, Chhoto-URL | Bitta serverli joylashtirishlar uchun ajoyib, sozlash kerak emas |
| **Redis** | Kutt, Dub.co (Upstash), Reduced.to | Asosiy kesh qatlami, ba'zan asosiy baza sifatida |
| **Cloudflare KV** | Sink | Edge-native kalit-qiymat; global past kechikish |
| **DynamoDB** | Maxsus AWS serverless amalga oshirishlar | Serverless arxitekturalarda keng tarqalgan |

### Keshlash Qatlamlari

| Yechim | Ishlatuvchi | Naqsh |
|---|---|---|
| **Redis** | Kutt, Dub.co, Reduced.to, Shlink | Cache-aside: avval Redis tekshirish, DB ga qaytish, miss da Redis to'ldirish |
| **In-Memory (application darajali)** | YOURLS (plaginlar orqali), Go-asoslangan | Jarayon ichida LRU kesh; eng sodda yondashuv |
| **CDN/Edge Cache** | Dub.co (Vercel Edge), Sink (Cloudflare) | CDN edge tugunlarida keshlanagan 301/302 javoblar; nolga yaqin kechikish |
| **Varnish** | Ba'zi YOURLS joylashtirishlar | PHP oldida teskari proksi kesh |

### Message Queue lar

| Yechim | Ishlatuvchi | Maqsad |
|---|---|---|
| **RabbitMQ** | Shlink (ixtiyoriy) | Tashriflash kuzatish uchun asinxron hodisa ishlov |
| **Upstash QStash** | Dub.co | Fon vazifalarni ishlov berish (analitika, webhooklar) |
| **Mercure** | Shlink (ixtiyoriy) | Real-time hodisa taqsimlash (SSE) |
| **Redis Pub/Sub** | Maxsus amalga oshirishlar | Yengil asinxron ishlov |
| **SQS** | AWS serverless amalga oshirishlar | Analitikani redirect yo'lidan ajratish |
| **Kafka** | Katta masshtabli enterprise (Bitly darajasi) | Yuqori o'tkazuvchanlik hodisa oqimi |

> **Muhim tushuncha:** Ko'pchilik ochiq kodli URL shortenerlar standart bo'yicha message queue **ISHLATMAYDI**. Analitika redirect yo'lida sinxron qayd etiladi. Faqat Shlink va Dub ichki asinxron hodisa qo'llab-quvvatlashiga ega. Yuqori o'tkazuvchanlik (>10K so'rov/sek) uchun analitikani queue orqali ajratish muhim.

### Konteynerlashtirish va Joylashtirish

| Yondashuv | Loyihalar | Eslatmalar |
|---|---|---|
| **Docker (rasmiy rasm)** | Shlink, Kutt, Reduced.to, Chhoto-URL | Shlink eng yaxshi Docker hikoyasiga ega |
| **Docker (jamoat rasmi)** | YOURLS | Jamoat tomonidan qo'llab-quvvatlanadigan `yourls` rasmi Docker Hub da |
| **Vercel** | Dub.co | Vercel platformasiga qattiq bog'langan |
| **Cloudflare Workers** | Sink | Edge-native joylashtirish |
| **Docker Compose** | Shlink, Kutt, Reduced.to | To'liq stek (app + DB + Redis) bitta compose faylda |
| **Kubernetes/Helm** | Shlink uchun jamoat chartlari | Ishlab chiqarish masshtabli joylashtirishlar uchun |
| **Oddiy server/VPS** | YOURLS, Polr | An'anaviy LAMP/LEMP stek |

---

## API Dizayn Naqshlari

### RESTful API Dizayni

Barcha yirik URL shortenerlar bo'ylab standart API naqshi REST konventsiyalariga amal qiladi:

**Asosiy Endpointlar (loyihalar bo'ylab konsensus):**

```
POST   /api/v1/short-urls          Qisqa URL yaratish
GET    /api/v1/short-urls          Qisqa URLlarni ro'yxatlash (pagination bilan)
GET    /api/v1/short-urls/{code}   Muayyan qisqa URL tafsilotlari
PATCH  /api/v1/short-urls/{code}   Qisqa URLni yangilash
DELETE /api/v1/short-urls/{code}   Qisqa URLni o'chirish
GET    /api/v1/short-urls/{code}/visits   Tashriflash/bosish statistikasi

GET    /{code}                      Redirect endpoint (ochiq, /api ostida emas)
```

### Platformalar API Taqqoslash

**Shlink API (eng keng qamrovli, OpenAPI hujjatlashtirilgan):**
```
POST   /rest/v3/short-urls
GET    /rest/v3/short-urls
GET    /rest/v3/short-urls/{shortCode}
PATCH  /rest/v3/short-urls/{shortCode}
DELETE /rest/v3/short-urls/{shortCode}
GET    /rest/v3/short-urls/{shortCode}/visits
GET    /rest/v3/tags
GET    /rest/v3/domains
GET    /rest/v3/visits/orphan
```

**Dub.co API (zamonaviy REST + SDK):**
```
POST   /api/links
GET    /api/links
GET    /api/links/{linkId}
PATCH  /api/links/{linkId}
DELETE /api/links/{linkId}
GET    /api/analytics
GET    /api/events
POST   /api/domains
```

**YOURLS API (legacy, action-asoslangan):**
```
POST   /yourls-api.php?action=shorturl&url=...&format=json
POST   /yourls-api.php?action=expand&shorturl=...
POST   /yourls-api.php?action=stats
POST   /yourls-api.php?action=url-stats&shorturl=...
```

### Autentifikatsiya Usullari

| Usul | Ishlatuvchi | Eslatmalar |
|---|---|---|
| **API Kalit (header)** | Kutt (`X-API-Key`), Shlink (`X-Api-Key`), Dub.co (`Authorization: Bearer`) | Eng keng tarqalgan; sodda, foydalanuvchi boshiga kalitlar |
| **API Kalit (query param)** | YOURLS (`?signature=...`) | Legacy yondashuv; kamroq xavfsiz (jurnallarda ko'rinadi) |
| **OAuth 2.0** | Dub.co | Uchinchi tomon integratsiyalari uchun |
| **JWT** | Reduced.to, ba'zi maxsus | Holatga bog'lanmagan, microserviceslar uchun yaxshi |

### Rate Limiting Yondashuvlari

| Yondashuv | Amalga oshirish | Ishlatuvchi |
|---|---|---|
| **Token bucket** | Redis asosida (`INCR` + `EXPIRE`) | Kutt, Dub.co |
| **Sliding window** | Redis sorted setlar | Dub.co (Upstash Ratelimit kutubxonasi) |
| **Fixed window** | Vaqt oynasi boshiga oddiy hisoblagich | YOURLS (plugin), Shlink |
| **API kalit boshiga limitlar** | Tarif/kalit asosida bosqichli limitlar | Dub.co |
| **IP-asoslangan** | Autentifikatsiya qilinmagan endpointlar uchun zaxira | Ko'pchilik loyihalar |

> Odatiy limitlar: yaratish endpointlari uchun 60-100 so'rov/daqiqa; redirect endpointlari odatda cheksiz yoki juda yuqori (10K+/daqiqa).

### Webhook Naqshlari

**Shlink** eng yetuk webhook tizimiga ega:
- `visit` hodisalarida tetiklanuvchi sozlanuvchi webhook URLlar
- Tashriflash ma'lumotlari (referrer, user agent, lokatsiya) bilan POST payload
- Real-time SSE uchun Mercure protokoli qo'llab-quvvatlash
- Asinxron hodisa ishlov uchun RabbitMQ integratsiya

**Dub.co** webhook naqshi:
- Ish fazosi boshiga sozlanuvchi webhook endpointlar
- Hodisalar: `link.created`, `link.updated`, `link.deleted`, `link.clicked`
- Tekshirish uchun imzolangan payloadlar (HMAC-SHA256)
- Eksponensial backoff bilan qayta urinish

---

## Arxitekturaviy Yondashuvlar Taqqoslashi

### 1. Monolitik Arxitektura

**Ishlatuvchi:** YOURLS, Polr, Kutt, Shlink

```
[Klient] → [Nginx/Apache] → [Monolitik Ilova] → [Ma'lumotlar Bazasi]
                                    |
                                    └──→ [Redis Kesh]
```

| Jihat | Tafsilot |
|---|---|
| **Xususiyatlari** | Bitta joylashtiriladigan birlik redirect va API/admin ni bajaradi |
| **Afzalliklari** | Joylashtirish va debugging soddaroq |
| **Masshtablash** | Avval vertikal, keyin load balancer orqali gorizontal |
| **To'siq** | Baza to'siq bo'ladi |
| **Qachon ishlatish** | <100K redirect/kun, kichik jamoa, o'z-o'zini joylashtirish |
| **Masshtablash yo'li** | Redis kesh qo'shish (10x yaxshilanish) → read replikalar → redirect xizmatini ajratish |

### 2. Mikroservislar Arxitekturasi

**Ishlatuvchi:** Katta masshtabli maxsus amalga oshirishlar (Bitly uslubi)

```
[Klient] → [Load Balancer]
                |
       +--------+--------+
       |                  |
[Redirect Xizmati]  [API Xizmati]  [Analitika Xizmati]
       |                  |                |
  [Redis Kesh]      [Yozish DB]     [Analitika DB]
       |                  |          (ClickHouse/
  [O'qish DB        [Queue]          Tinybird)
   Replika]              |
                   [Worker Xizmati]
```

| Jihat | Tafsilot |
|---|---|
| **Xususiyatlari** | Redirect xizmati juda yengil; analitika asinxron; har bir xizmat mustaqil masshtablanadi |
| **Redirect xizmati** | Go/Rust da yozilishi mumkin minimal kechikish uchun |
| **Qachon ishlatish** | >1M redirect/kun, bir nechta jamoalar, yuqori mavjudlik talablari |

### 3. Serverless Arxitektura

**Misol: AWS Lambda + DynamoDB + API Gateway**

```
[Klient] → [API Gateway / CloudFront]
                   |
            +------+------+
            |             |
      [Lambda:        [Lambda:
       Redirect]       Create]
            |             |
       [DynamoDB]    [DynamoDB]
            |
      [Kinesis/SQS] → [Lambda: Analitika] → [S3/Athena]
```

| Jihat | Tafsilot |
|---|---|
| **Xususiyatlari** | Boshqarish uchun nol server, nolgacha avtomatik masshtablash |
| **Afzalliklari** | Past trafik uchun xarajat samarali, DynamoDB bir raqamli ms |
| **Kamchiliklari** | Cold start kechikishi (~100-500ms), API Gateway ~10-20ms overhead |
| **Qachon ishlatish** | O'zgaruvchan/bashorat qilinmaydigan trafik, ops sig'imsiz kichik jamoa |

> **Muhim muammo:** Lambda cold startlar redirect kechikishiga 100-500ms qo'shishi mumkin. Provisioned concurrency hal qiladi, lekin xarajat qo'shadi.

### 4. Edge Computing Arxitekturasi

**Ishlatuvchi:** Dub.co (Vercel Edge), Sink (Cloudflare Workers)

```
[Klient] → [Edge Tarmoq (200+ PoP dunyo bo'ylab)]
                   |
            [Edge Funksiya]
                   |
            [Edge KV Store] yoki [Edge Kesh bilan Baza]
                   |
            [Yozishlar uchun markaziy baza]
```

| Jihat | Tafsilot |
|---|---|
| **Xususiyatlari** | Global sub-10ms redirect kechikishi (kod eng yaqin PoP da ishlaydi) |
| **Afzalliklari** | Cold start yo'q (V8 isolatelar), eng yaxshi foydalanuvchi tajribasi |
| **Kamchiliklari** | Vendor lock-in, so'rov boshiga cheklangan hisoblash, eventually consistent o'qishlar |
| **Qachon ishlatish** | Global auditoriya, kechikishga sezgir, zamonaviy infratuzilma |

### Arxitektura Taqqoslash Xulosa Jadvali

| Mezon | Monolitik | Mikroservislar | Serverless | Edge |
|---|---|---|---|---|
| **Redirect Kechikish** | 20-100ms | 5-30ms | 50-500ms (sovuq)/10-30ms (issiq) | **1-10ms** |
| **Murakkablik** | Past | Yuqori | O'rta | O'rta |
| **Past masshtabda xarajat** | Belgilangan (server) | Yuqori (ko'p xizmat) | Nolga yaqin | Nolga yaqin |
| **Yuqori masshtabda xarajat** | O'rta | O'rta | Yuqori | O'rta |
| **Masshtablash sa'yi** | Qo'lda | Xizmat boshiga | Avtomatik | Avtomatik |
| **O'z joylashtirish qulayligi** | Oson | Qiyin | N/A (bulut) | N/A (bulut) |
| **Kerakli jamoa hajmi** | 1-2 | 3-5+ | 1-2 | 1-2 |

---

## Ishlash Ko'rsatkichlari

### O'tkazuvchanlik Raqamlari

| Yechim/Stek | Redirect O'tkazuvchanlik | Eslatmalar |
|---|---|---|
| **Go + Redis** | 50,000-100,000+ so'rov/sek | Bitta instansiya; Go goroutine modeli + Redis pipelining |
| **Rust (Actix) + Redis** | 60,000-120,000+ so'rov/sek | Go ga o'xshash; biroz yuqoriroq raw o'tkazuvchanlik |
| **Node.js (Express) + Redis** | 10,000-30,000 so'rov/sek | Bitta instansiya; I/O-bound redirect uchun event loop samarali |
| **PHP (Shlink) + Redis** | 2,000-5,000 so'rov/sek | PHP-FPM worker havzasi boshiga; workerlar bilan masshtablanadi |
| **PHP (YOURLS) keshsiz** | 500-1,500 so'rov/sek | Har bir so'rov uchun MySQL so'rovlari bilan to'siqli |
| **Cloudflare Workers + KV** | Amalda cheksiz | 100K+ so'rov/sek global taqsimlangan |
| **AWS Lambda + DynamoDB** | ~10,000 bir vaqtdagacha avtomatik masshtablash | Mintaqa boshiga; cold startlar cheklov |

### Redirect Kechikish

| Stek | P50 Kechikish | P99 Kechikish | Eslatmalar |
|---|---|---|---|
| **Edge (CF Workers/Vercel)** | 1-5ms | 10-20ms | Eng tez; originga tarmoq o'tishi yo'q |
| **Go/Rust + Redis** | 1-3ms | 5-15ms | Redis qidirish <1ms, ilova overhead minimal |
| **Node.js + Redis** | 2-5ms | 10-30ms | Event loop overhead biroz yuqoriroq |
| **PHP + Redis** | 5-15ms | 30-80ms | PHP-FPM jarayon boshlash overhead |
| **PHP + MySQL (keshsiz)** | 10-50ms | 100-300ms | MySQL so'rov ustunlik qiladi |
| **Lambda + DynamoDB (issiq)** | 10-20ms | 30-50ms | DynamoDB bir raqamli ms + Lambda overhead |
| **Lambda + DynamoDB (sovuq)** | 200-800ms | 1-3s | Cold start ustunlik qiladi |

### Asosiy Ishlash Tushunchalari

1. **Redirect yo'li muhim issiq yo'l.** Iloji boricha kam I/O operatsiyalariga tegrishi kerak. Ideal redirect: Redis/xotira keshdan o'qish → 301/302 qaytarish. Redirect yo'lida DB yozish yo'q.

2. **Analitika asinxron bo'lishi kerak.** Bosishlarni redirect yo'lida sinxron qayd etish 5-50ms kechikish qo'shadi. Eng yaxshi: hodisani queue ga (Redis, SQS, Kafka) chiqarish va asinxron ishlov berish.

3. **301 vs 302 ishlashga ta'sir qiladi.** 301 brauzerlar tomonidan keshlanadi, server yukini kamaytiradi lekin analitikani kamroq aniq qiladi. 302 har bir bosish serverga borishini ta'minlaydi. Ko'pchilik shortenerlar shu sababli 302 ishlatadi.

4. **Kesh hit nisbati hamma narsa.** URL kirish Zipf taqsimotiga amal qiladi. Eng ko'p botiladigan 10K URLlarni Redis da keshlash odatda 90%+ trafikka xizmat qiladi.

5. **Connection pooling muhim.** Har bir so'rov uchun yangi DB ulanish ochish 5-20ms qo'shadi. PgBouncer, MySQL connection pool, Prisma connection pool zarur.

---

## Xulosa Taqqoslash Matritsasi

| Funksiya | YOURLS | Kutt | Shlink | Polr | Dub.co | Sink |
|---|---|---|---|---|---|---|
| **Yulduzlar** | ~10.7K | ~8.4K | ~3.2K | ~5K | ~19K+ | ~2.5K |
| **Faollik** | Qo'llab-quv. | Sekin | **Juda Faol** | O'lik | **Juda Faol** | Faol |
| **Til** | PHP | TypeScript | PHP | PHP | TypeScript | TypeScript |
| **Framework** | Yo'q | Express | Mezzio | Laravel 5 | Next.js 14 | Nuxt |
| **Baza** | MySQL | PostgreSQL | MySQL/PG/SQLite/MSSQL | MySQL/PG/SQLite | PlanetScale | CF KV |
| **Kesh** | Plugin | Redis | Redis (ixr) | Yo'q | Upstash | Edge (CF) |
| **Queue** | Yo'q | Yo'q | RabbitMQ/Mercure | Yo'q | QStash | Yo'q |
| **Docker** | Jamoat | Rasmiy | **Rasmiy** | Yo'q | Yo'q (Vercel) | Yo'q (CF) |
| **O'z Joylashtirish** | **Juda Oson** | O'rta | Oson | O'rta | Juda Qiyin | Oson (CF) |
| **API Sifati** | Legacy | Yaxshi | **Ajoyib** | Yaxshi | **Ajoyib** | Oddiy |
| **Litsenziya** | MIT | MIT | MIT | GPL-2.0 | AGPL-3.0 | MIT |
| **Eng Yaxshi** | Oddiy o'z-o'zi | Zamonaviy o'z-o'zi | Ko'p funksiyali | Foydalanmang | SaaS/bulut | Edge/CF |

---

## POC Uchun Tavsiya

Sizning jamoangiz uchun alternativ loyiha qurish maqsadida:

1. **O'z-o'zini joylashtirish soddaligi uchun:** Shlink yondashuvini model qiling (API-birinchi, Docker-native, bir nechta DB qo'llab-quvvatlash)
2. **Maksimal ishlash uchun:** Go yoki Rust redirect xizmati + Redis kesh + queue orqali asinxron analitika
3. **Zamonaviy dasturchi tajribasi uchun:** TypeScript/Next.js Dub.co ga o'xshash, lekin soddaroq o'z-o'zini joylashtirish bog'liqliklari bilan
4. **Global past kechikish uchun:** Edge arxitektura (Cloudflare Workers + KV) Sink ga o'xshash
5. **Redirect issiq yo'li uchun:** G'olib naqsh: Edge/CDN kesh → Redis/xotira kesh → Baza zaxirasi, analitika asinxron yoziladi
