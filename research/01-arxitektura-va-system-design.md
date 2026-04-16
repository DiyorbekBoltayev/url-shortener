# URL Shortener — Arxitektura va System Design

## Mundarija
- [Umumiy Arxitektura](#umumiy-arxitektura)
- [Asosiy Komponentlar](#asosiy-komponentlar)
- [URL Qisqartirish Jarayoni (Write Path)](#url-qisqartirish-jarayoni-write-path)
- [Redirect Jarayoni (Read Path)](#redirect-jarayoni-read-path)
- [Read va Write Pathlarni Ajratish](#read-va-write-pathlarni-ajratish)
- [URL Kodlash Mexanizmlari](#url-kodlash-mexanizmlari)
- [Ma'lumotlar Bazasi Dizayni](#malumotlar-bazasi-dizayni)
- [Keshlash Strategiyasi](#keshlash-strategiyasi)
- [Masshtablash](#masshtablash)
- [Yuqori Darajadagi Mavjudlik (High Availability)](#yuqori-darajadagi-mavjudlik)

---

## Umumiy Arxitektura

URL shortener — bu asosan **o'qish (read) og'ir** tizim. Odatda read:write nisbati **100:1** dan **1000:1** gacha bo'ladi. Ya'ni har 1 ta URL yaratilganda, u 100-1000 marta bosiladi (redirect).

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Foydalanuvchi  │────▶│  Load Balancer │────▶│  API/Web Server  │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │              │              │
                              ┌─────▼─────┐  ┌────▼────┐  ┌─────▼──────┐
                              │   Redis    │  │   DB    │  │  Analytics  │
                              │   Cache    │  │ (Primary)│  │  Service   │
                              └───────────┘  └────┬────┘  └─────┬──────┘
                                                   │              │
                                             ┌─────▼─────┐  ┌────▼─────┐
                                             │ DB Replica │  │  Kafka/  │
                                             │  (Read)    │  │   SQS    │
                                             └───────────┘  └──────────┘
```

---

## Asosiy Komponentlar

| Komponent | Vazifasi |
|---|---|
| **Load Balancer** | Kiruvchi trafikni web serverlar o'rtasida taqsimlaydi (masalan: AWS ALB, Nginx, HAProxy) |
| **API Gateway** | Rate limiting, autentifikatsiya, marshrutlash, SSL termination |
| **Web/Application Serverlar** | URL qisqartirish va redirect logikasini bajaruvchi stateless xizmatlar |
| **Ma'lumotlar Bazasi** | URL xaritalarini saqlash (qisqa kod → uzun URL) |
| **Kesh Qatlami** | Tez-tez foydalaniladigan URLlar uchun in-memory saqlash (Redis/Memcached) |
| **ID Generatsiya Xizmati** | Qisqa kodlarga aylantiriluvchi noyob IDlar yaratadi |
| **Analitika Xizmati** | Bosish (click), referrer, geolokatsiya kuzatadi (ko'pincha asinxron, message queue orqali) |
| **CDN** | Eng ko'p botiladigan URLlar uchun edge lokatsiyalarida 301/302 redirect beradi |

---

## URL Qisqartirish Jarayoni (Write Path)

Foydalanuvchi yangi URL yaratmoqchi bo'lganda:

```
1. Klient → POST /api/shorten { "long_url": "https://example.com/juda/uzun/yol" }
2. API Gateway → autentifikatsiya + rate limiting
3. Application Server → URL validatsiyasi (format, reachability, qora ro'yxat)
4. (Ixtiyoriy) Deduplikatsiya tekshiruvi → bu URL allaqachon qisqartirilganmi?
5. ID Generatsiya → noyob ID yaratish (counter, Snowflake, yoki DB auto-increment)
6. Kodlash → raqamli ID ni Base62 stringga aylantirish (masalan: 12345 → "dnh")
7. Saqlash → { short_code: "dnh", long_url: "https://...", created_at, user_id, ttl }
8. (Ixtiyoriy) Kesh isitish → write-through orqali keshga yozish
9. Javob → https://qisqa.uz/dnh qaytarish
```

---

## Redirect Jarayoni (Read Path)

Foydalanuvchi qisqa URLni bosganda:

```
1. Brauzer → GET https://qisqa.uz/dnh
2. Load Balancer → so'rovni application serverga yo'naltiradi
3. Application Server → "dnh" qisqa kodni ajratib oladi
4. Kesh tekshiruvi → Redis/Memcached da qidirish
   ├── Cache HIT (~80-90% holatlarda) → 6-bosqichga o'tish
   └── Cache MISS → 5-bosqichga o'tish
5. DB so'rov → Ma'lumotlar bazasidan qidirish, topilsa keshga yozish
6. (Asinxron) → Kafka/SQS ga click hodisasini yuborish (analitika uchun)
7. HTTP 301 yoki 302 → Location: https://example.com/juda/uzun/yol
```

### 301 vs 302 Redirect

| Xususiyat | 301 (Doimiy) | 302 (Vaqtinchalik) |
|---|---|---|
| **Brauzer keshlashi** | Ha (brauzer eslab qoladi) | Yo'q (har safar serverga murojaat) |
| **SEO** | Link equity manzil URL ga o'tadi | Link equity qisqa URL da qoladi |
| **Analitika** | Takroriy bosishlarni ko'rmaysiz | Har bir bosishni kuzatish mumkin |
| **Server yuki** | Kamroq (brauzer keshdan oladi) | Ko'proq (har safar server) |
| **Qachon ishlatish** | Analitika kerak bo'lmaganda | **Analitika muhim bo'lganda (tavsiya)** |

> **Bitly** va ko'pchilik analitika-yo'naltirilgan platformalar **302** ishlatadi, chunki har bir bosishni kuzatish — ularning mahsuloti.

---

## Read va Write Pathlarni Ajratish

Bu muhim arxitekturaviy qaror, chunki:

- **Write path** — biroz kechikish qabul qilinadi (200-500ms)
- **Read path** — juda tez bo'lishi kerak (**<50ms** maqsad), chunki foydalanuvchi navigatsiyasini to'sib turadi
- Ma'lumotlar bazasida **read replikalar** ishlatilishi mumkin — yozish primary ga, o'qish replikalarga
- Kesh qatlami asosan read pathga xizmat qiladi
- Ba'zi arxitekturalar read va write uchun butunlay alohida xizmatlar ishlatadi (**CQRS pattern**)

---

## URL Kodlash Mexanizmlari

### A Yondashuv: Counter + Base62 Kodlash (Tavsiya etiladi)

Bu eng ko'p ishlatiladigan ishlab chiqarish yondashuvi:

1. Noyob butun son yaratish (auto-increment counter yoki taqsimlangan counter)
2. Base62 belgilar to'plami orqali aylantirish: `a-zA-Z0-9` (62 ta belgi)

**Base62 kodlash misoli:**
```
ID = 12345
12345 / 62 = 199 qoldiq 7  → charset[7]  = 'h'
199   / 62 = 3   qoldiq 11 → charset[11] = 'l'
3     / 62 = 0   qoldiq 3  → charset[3]  = 'd'
Natija: "dlh" (qoldiqlarni pastdan yuqoriga o'qing)
```

**Qisqa kod uzunligi hisoblari:**

| Uzunlik | Kombinatsiyalar (62^n) | Sig'im |
|---------|------------------------|--------|
| 5 | 916 million | ~900M URL |
| 6 | 56.8 milliard | ~57B URL |
| **7** | **3.52 trillion** | **~3.5T URL** |
| 8 | 218 trillion | ~218T URL |

> **7 belgi standart tanlov** — 3.5 trillion deyarli har qanday holat uchun yetarli. Bitly ham 7 belgi ishlatadi.

**Afzalliklar:** Collision yo'q (har bir ID noyob), deterministik, qisqa kodlar
**Kamchiliklar:** Ketma-ket IDlar bashorat qilish mumkin (shuffling/bijective mapping bilan hal qilinadi)

### B Yondashuv: MD5/SHA256 Xeshlash

1. Uzun URLni xeshlash: `MD5("https://example.com/...") = "5d41402abc4b2a76b9719d911017c592"`
2. Birinchi 7 belgini olish (yoki birinchi N baytni Base62 sifatida kodlash)

**Afzalliklar:** Bir xil URL har doim bir xil xesh beradi (tabiiy deduplikatsiya). Counter xizmati kerak emas.
**Kamchiliklar:**
- **Collisionlar muqarrar** — birthday paradox tufayli ~1 million URL bilan 7 belgili qirqilgan xeshlar uchun sezilarli collision ehtimoli
- Collisionlarni boshqarish kerak: bazani tekshirish, agar collision bo'lsa, salt/counter qo'shib qayta xeshlash
- Collision hal qilish kechikish va murakkablik qo'shadi

### C Yondashuv: Snowflake ID / Taqsimlangan ID Generatsiya

Twitterning Snowflake tizimi 64-bitli noyob IDlar yaratadi:

```
| 1 bit ishlatilmagan | 41 bit vaqt tamg'asi | 5 bit datacenter | 5 bit mashina | 12 bit ketma-ketlik |
```

- **41 bit vaqt tamg'asi** → ~69 yil millisekund aniqligi
- **5 + 5 bit** → 32 datacenter × 32 mashina = 1024 ishchi
- **12 bit ketma-ketlik** → har bir ishchi uchun millisekundiga 4096 ID
- Umumiy o'tkazuvchanlik: har bir datacenter uchun **sekundiga 4 million ID**

### D Yondashuv: Kalit Generatsiya Xizmati (KGS)

Eng ishonchli ishlab chiqarish yondashuvi:

1. KGS oldindan millionlab tasodifiy 7 belgili Base62 stringlar yaratadi va `keys_available` jadvaliga saqlaydi
2. Application serverlar KGS dan bir partiya kalitlar (masalan, 1000 ta) so'raydi
3. Har bir server mahalliy buferda mavjud kalitlarga ega — URL yaratish bir zumda
4. Agar server ishdan chiqsa, ishlatilmagan kalitlar yo'qoladi (7 belgili masshtabda qabul qilinadigan isrof)

### Collision Oldini Olish Xulosa

| Strategiya | Collision Xavfi | Yechim |
|---|---|---|
| Auto-increment counter | Yo'q | Yagona nosozlik nuqtasi; shardlangan counterlar |
| Snowflake | Yo'q | Soat farqi boshqarish kerak |
| KGS (Kalit Generatsiya) | Yo'q | Alohida xizmat kerak |
| Xesh qirqish | O'rta-Yuqori | Tekshirish va qayta urinish |
| Tasodifiy generatsiya | Past (7+ belgi bilan) | Tekshirish va qayta urinish |

---

## Ma'lumotlar Bazasi Dizayni

### Asosiy Sxema

```sql
-- Asosiy URL xaritalash jadvali
CREATE TABLE url_mappings (
    id            BIGINT PRIMARY KEY,          -- raqamli ID (Base62 kod manbai)
    short_code    VARCHAR(10) UNIQUE NOT NULL,  -- Base62 kodlangan qisqa kod
    long_url      TEXT NOT NULL,                -- asl URL (~2048 belgigacha)
    user_id       BIGINT,                       -- yaratuvchi (anonim uchun null)
    created_at    TIMESTAMP DEFAULT NOW(),
    expires_at    TIMESTAMP,                    -- ixtiyoriy TTL
    click_count   BIGINT DEFAULT 0,             -- denormalizatsiyalangan hisoblagich
    is_active     BOOLEAN DEFAULT TRUE
);

-- Redirect qidiruvlari uchun indeks (issiq yo'l)
CREATE INDEX idx_short_code ON url_mappings(short_code);

-- Deduplikatsiya uchun indeks (ixtiyoriy)
CREATE INDEX idx_long_url ON url_mappings(long_url);

-- Analitika jadvali (ko'pincha alohida bazada)
CREATE TABLE click_events (
    id            BIGINT PRIMARY KEY,
    short_code    VARCHAR(10) NOT NULL,
    clicked_at    TIMESTAMP DEFAULT NOW(),
    referrer      TEXT,
    user_agent    TEXT,
    ip_address    INET,
    country       VARCHAR(2),
    device_type   VARCHAR(20)
);
```

### SQL vs NoSQL Tanlash

| Ma'lumotlar Bazasi | Afzalliklari | Kamchiliklari | Kim Ishlatadi |
|---|---|---|---|
| **PostgreSQL** | ACID, kuchli izchillik, yetuk indekslash, JSON qo'llab-quvvatlash | Gorizontal masshtablash qiyin | Instagram (shardlangan PG) |
| **MySQL** | PG ga o'xshash, yaxshi tushunilgan sharding (Vitess) | Xuddi shunday gorizontal masshtablash muammolari | Ko'plab startaplar |
| **DynamoDB** | To'liq boshqariladigan, bir raqamli ms kechikish, avtomatik masshtablash, ichki TTL | Katta masshtabda qimmat, standart bo'yicha eventual consistent | AWS-markaziy arxitekturalar |
| **Cassandra** | Chiziqli gorizontal masshtablash, yuqori yozish o'tkazuvchanligi | Operatsion murakkablik, joinlar yo'q | Katta hajmli tizimlar |
| **MongoDB** | Moslashuvchan sxema, ichki sharding | Bu oddiy kalit-qiymat holati uchun kam samarali | Ba'zi loyihalar |
| **Redis (asosiy)** | Juda tez, lekin saqlash kelishuvlari bor | Ma'lumot yo'qotish xavfi, xotira qimmat | Kichik masshtab yoki faqat kesh |

> **Tavsiya:** Katta masshtab (milliardlab URL) uchun **DynamoDB** yoki **Cassandra**, o'rtacha masshtab (millionlab URL) uchun **PostgreSQL**.

### Sharding Strategiyalari

**Eng yaxshi amaliyot:** `short_code` bo'yicha **consistent hashing** yordamida shardlash. Bu redirect yo'li (short_code bo'yicha qidirish) aynan bitta shardga murojaat qilishini ta'minlaydi.

| Sharding kaliti | Afzalligi | Kamchiligi |
|---|---|---|
| **short_code xeshi** | Bir xil taqsimot, O(1) qidirish | - |
| **user_id** | Foydalanuvchi so'rovlari uchun yaxshi | Redirect uchun scatter-gather kerak |
| **Yaratilish sanasi** | TTL/tozalash uchun yaxshi | Qidirish uchun yomon |

### Indekslash Strategiyalari

- **Asosiy indeks** `short_code` bo'yicha — bu redirect uchun issiq qidirish yo'li
- **Ikkilamchi indeks** `long_url` bo'yicha — faqat deduplikatsiya kerak bo'lsa
- **TTL indeks** `expires_at` bo'yicha — muddati o'tgan URLlarni avtomatik tozalash uchun
- Analitika uchun: `clicked_at` bo'yicha vaqt seriyali indekslar

---

## Keshlash Strategiyasi

### 80/20 Qoidasi (Pareto Printsipi)

URL shortenerda kuchli qo'llaniladi: taxminan **20% qisqa URLlar 80% umumiy redirect trafikini oladi**. Ba'zi URLlar viral bo'lib, millionlab bosishlar oladi.

**Odatiy kesh hit nisbati: 85-95%** — yaxshi sozlangan URL shortener keshi uchun.

### Kesh Hajmi Hisoblash

Misol: 100M umumiy URL, 20% "issiq" = 20M URL keshlash uchun.
Har bir yozuv: ~200 bayt (short_code + long_url + metadata).
Jami: 20M × 200 bayt = **~4 GB** — bitta Redis instansiyasiga oson sig'adi.

### Redis vs Memcached

| Xususiyat | Redis | Memcached |
|---|---|---|
| Ma'lumot tuzilmalari | Boy (stringlar, xeshlar, to'plamlar) | Faqat kalit-qiymat |
| Saqlash (Persistence) | RDB + AOF | Yo'q |
| Replikatsiya | Ichki primary-replica | Tabiiy emas |
| TTL qo'llab-quvvatlash | Ha, har bir kalit uchun | Ha |

> **Redis standart tanlov** — TTL qo'llab-quvvatlash va replikatsiya tufayli.

### Keshlash Naqshlari

**Cache-Aside (Read-Through) — Redirect uchun tavsiya:**
```
1. Keshda short_code ni tekshirish
2. HIT bo'lsa → long_url qaytarish
3. MISS bo'lsa → bazadan so'rash → keshga yozish → long_url qaytarish
```

**Write-Through — Qisqartirish uchun ixtiyoriy:**
```
1. Bazaga yozish
2. Bir vaqtda keshga yozish
3. Muvaffaqiyat qaytarish
```

> Bu yaratilgandan keyingi birinchi redirect kesh missga uchramasligini ta'minlaydi.

### Kesh Eviction Siyosatlari

- **LRU (Least Recently Used):** Eng yaqinda ishlatilmagan yozuvlarni o'chiradi. Yaqinda viral bo'lgan URLlar keshda qoladi.
- **LFU (Least Frequently Used):** Eng kam foydalanilgan yozuvlarni o'chiradi. Barqaror trafikli URLlar uchun yaxshiroq.
- **TTL-asoslangan:** Kesh yozuvlarida TTL o'rnatish (masalan, 24 soat).

> Redis da `allkeys-lfu` URL shortener uchun eng yaxshi tanlov.

### Cache Stampede (Thundering Herd) Oldini Olish

Mashhur URLning kesh yozuvi muddati tugaganda, yuzlab bir vaqtdagi so'rovlar bazaga murojaat qilishi mumkin:

1. **Qulflash asosida (Singleflight):** Faqat bitta so'rov bazaga boradi; boshqalari kesh to'ldirilishini kutadi
2. **Ehtimollik asosida erta yangilash:** Kesh muddati tugashidan oldin tasodifiy ravishda yangilanadi
3. **Stale-while-revalidate:** Eskirgan kesh qiymatini darhol berish va fonida yangilash
4. **TTL siz + foniy yangilash:** Eng issiq URLlar uchun TTL o'rnatmasdan, fon jarayoni keshni davriy yangilaydi

---

## Masshtablash

### Trafik Hisoblash (Back-of-Envelope)

**Kichik masshtab (startap):**
- 1M URL/oy yaratiladi
- ~0.4 yozish/sek, ~40 o'qish/sek
- Bitta server + bitta baza yetarli

**O'rta masshtab (o'suvchi mahsulot):**
- 100M URL/oy
- ~40 yozish/sek, ~4,000 o'qish/sek
- Keshlash, read replikalar, bir nechta app serverlar kerak

**Katta masshtab (Bitly darajasi):**
- Milliardlab bosish/oy
- ~1,000-3,000 yozish/sek, ~100,000-300,000 o'qish/sek (cho'qqi)
- Shardlangan baza, taqsimlangan kesh, ko'p mintaqali, CDN kerak

### Gorizontal Masshtablash

**Stateless Application Qatlami:**
- Application serverlar holat saqlamaydi — barcha holat bazada va keshda
- Load balancer orqasida auto-scaling guruhlar bilan gorizontal masshtablanadi
- Kubernetes yoki ECS konteyner orkestratsiyasi uchun

**Ma'lumotlar Bazasi Qatlami:**
- **Read replikalar:** O'qish yukini boshqarish uchun replikalar qo'shish
- **Sharding:** Bitta primary yozish yukini ko'tara olmaganda bir nechta instansiyalar bo'ylab taqsimlash
- **Connection pooling:** PgBouncer yoki ProxySQL orqali ulanishlarni boshqarish

**Kesh Qatlami:**
- **Redis Cluster:** Bir nechta Redis tugunlari bo'ylab avtomatik sharding
- **Redis Sentinel:** Avtomatik failover bilan yuqori mavjudlik
- **Odatiy sozlash:** Har bir primary uchun 1 replika bilan 3-tugunli Redis cluster

### CDN Redirect Uchun

CDN (CloudFlare, CloudFront, Fastly) redirect javoblarini edge lokatsiyalarida keshlashi mumkin:

- `Cache-Control` headeri bilan 301/302 javoblarni keshlash
- CDN origin serverlaringizga murojaat qilmasdan redirectni beradi
- **Kechikishning katta kamayishi** — eng yaqin edge dan (5-20ms vs 50-200ms)
- **Ogohlantirish:** Bosish kuzatishni qiyinlashtiradi. Yechim: CDN edge funksiyalari (CloudFlare Workers, Lambda@Edge) orqali redirectdan oldin bosishlarni qayd etish

### Rate Limiting

Suiiste'molning oldini olish uchun muhim:

| Limiter | Qamrov | Odatiy Limit |
|---|---|---|
| URL yaratish | API kalit / foydalanuvchi boshiga | 100 URL/soat |
| URL yaratish | IP boshiga (anonim) | 10 URL/soat |
| Redirectlar | Qisqa kod boshiga | 1000 so'rov/sek |
| Redirectlar | Global | Infratuzilma sig'imi bilan cheklangan |

> Amalga oshirish: Token bucket yoki sliding window algoritmi, Redis da saqlanadi.

---

## Yuqori Darajadagi Mavjudlik

### Ko'p Mintaqali Joylashtirish

**Active-Passive:**
- Bitta asosiy mintaqa barcha yozishlarni bajaradi
- Ikkilamchi mintaqa replikatsiya qilingan ma'lumotlarni qabul qiladi va o'qishlarni bajaradi
- Nosozlikda ikkilamchi asosiyga ko'tariladi
- Soddaroq, lekin sekinroq failover (daqiqalar)

**Active-Active:**
- Ikkala mintaqa ham o'qish VA yozishni bajaradi
- ID generatsiyasi uchun nizoni hal qilish kerak (mintaqa prefiksli IDlar yoki Snowflake bilan)
- Murakkabroq, lekin deyarli bir zumda failover va global past kechikish
- **Bitly va boshqa katta shortenerlar active-active ishlatadi**

### Failover Strategiyalari

| Komponent | Strategiya | Qayta Tiklash Vaqti |
|---|---|---|
| **Ma'lumotlar bazasi** | Avtomatlashtirilgan failover (AWS RDS Multi-AZ, Patroni) | 30-60 sekund |
| **Kesh** | Redis Sentinel avtomatik replica ko'tarish | Sekundlar |
| **Application** | Load balancer health checklarni bajaradi, auto-scaling | Sekundlar |

### Ma'lumotlar Izchilligi Modellari

**URL xaritalash (asosiy ma'lumotlar) uchun:**
- **Yozish uchun kuchli izchillik:** URL yaratilganda, qisqa kod darhol hal qilinishi kerak
- **O'qish uchun eventual consistency qabul qilinadi:** Bir necha sekundlik replikatsiya kechikishi yaxshi

**Analitika ma'lumotlari uchun:**
- **Eventual consistency yaxshi:** Bosish hisoblari real vaqt aniqligiga muhtoj emas
- Hodisalarni Kafka/SQS orqali asinxron qayta ishlash

**Mintaqalararo izchillik uchun:**
- **Eventual consistency amaliy tanlov:** Mintaqalararo sinxron replikatsiya har bir yozishga 50-150ms kechikish qo'shadi
- Qisqa kodlar global noyob bo'lgani uchun nizosiz

---

## Asosiy Dizayn Qarorlari Xulosa Jadvali

| Qaror | Tavsiya Etilgan Tanlov | Sabab |
|---|---|---|
| Qisqa kod generatsiya | Counter + Base62 yoki KGS | Collision yo'q, oddiy, tez |
| Qisqa kod uzunligi | 7 belgi | 3.5T kombinatsiya, har qanday masshtab uchun yetarli |
| Ma'lumotlar bazasi | DynamoDB (katta) yoki PostgreSQL (o'rta) | Masshtab vs oddiylik kelishuvi |
| Kesh | Redis LFU eviction bilan | Issiq URL kirish naqshlariga eng mos |
| Keshlash naqshi | Read-through + Write-through | Birinchi kirish va keyingi o'qishlarni optimallashtiradi |
| Redirect holati | 302 (agar kuzatish kerak) yoki 301 (agar kerak emas) | 302 bosish analitikasini saqlaydi |
| ID generatsiya | Snowflake yoki KGS | Taqsimlangan tizimlarda ishlaydi |
| Izchillik | Yozish uchun kuchli, o'qish/analitika uchun eventual | To'g'rilik va ishlash muvozanati |
| Ko'p mintaqali | Active-active mintaqa prefiksli IDlar bilan | Eng yaxshi mavjudlik va kechikish |
