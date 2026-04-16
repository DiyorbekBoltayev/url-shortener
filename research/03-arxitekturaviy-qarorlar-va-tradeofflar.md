# URL Shortener — Arxitekturaviy Qarorlar va Trade-offlar

## Mundarija
- [Asosiy Arxitekturaviy Qarorlar](#asosiy-arxitekturaviy-qarorlar)
- [Masshtablash Muammolari](#masshtablash-muammolari)
- [Dizayn Muammolari](#dizayn-muammolari)
- [Ma'lumotlar Modellashtirish](#malumotlar-modellashtirish)
- [Xavfsizlik Masalalari](#xavfsizlik-masalalari)
- [Sig'im Hisoblash](#sigim-hisoblash)

---

## Asosiy Arxitekturaviy Qarorlar

### 1. 301 (Doimiy) vs 302 (Vaqtinchalik) Redirect

Bu eng muhim dastlabki qarorlardan biri.

#### 301 Moved Permanently

- Brauzer (va oraliq proksilar) redirectni **keshlaydi**. Keyingi tashriflarda brauzer serveringizga murojaat qilmasdan to'g'ridan-to'g'ri uzun URLga boradi
- **SEO:** Qidiruv tizimlari link equitiyni (PageRank) qisqa URLdan manzil URLga o'tkazadi. Manzil URL vaqt o'tishi bilan qidiruv indekslarida qisqa URL o'rnini egallaydi
- **Analitika:** Brauzer xaritani keshlashi sababli, bir xil brauzerdan takroriy bosishlarni **ko'rmaysiz**. Bosish hisoblagichingiz kam ko'rsatadi
- **Ishlash:** Mashhur linklar uchun serverlaringizga kam yuk

#### 302 Found (Vaqtinchalik)

- Brauzer redirectni **keshlamaydi**. Har bir bosish serveringiz orqali o'tadi
- **SEO:** Qidiruv tizimlari qisqa URLni kanonik reference sifatida ko'radi
- **Analitika:** Takroriy tashriflar ham dahil, **har bir bosishni kuzatish** mumkin
- **Ishlash:** Serverlaringizga yuqoriroq yuk

#### Qachon qaysi birini ishlatish kerak?

| Foydalanish holati | Tavsiya | Sabab |
|---|---|---|
| Analitika-yo'naltirilgan mahsulot (Bitly, Rebrandly) | **302** | Har bir bosishni kuzatish kerak |
| Sof yo'naltirish, analitika kerak emas | **301** | Server yukini kamaytiradi, manzil SEO uchun yaxshi |
| Marketing kampaniyalari (vaqt cheklangan) | **302** | Keyinchalik qisqa URLni qayta maqsadlashi mumkin |
| Doimiy resurs ko'chishi | **301** | To'g'ri semantik ma'no |
| A/B testlash manzil URLlari | **302** | Manzil o'zgarishi mumkin |

> **Bitly** standart bo'yicha 301 ishlatadi, lekin ba'zi linklarni 307 ga o'tkazdi. Ko'pchilik analitika-yo'naltirilgan shortenerlar aslida **302 yoki 307** ishlatadi.

---

### 2. Base62 Kodlash vs Xeshlash

#### A Yondashuv: Counter/ID + Base62 Kodlash

Monoton o'suvchi counter raqamli ID yaratadi, keyin Base62 ga kodlanadi.

| Jihat | Tafsilot |
|---|---|
| **Afzalliklari** | Noyoblik kafolatlangan (collision yo'q), qisqa kodlar, deterministik, oddiy |
| **Kamchiliklari** | Ketma-ket IDlar bashorat qilish mumkin, markazlashtirilgan counter kerak |
| **Xavfsizlik** | Hujumchilar barcha URLlarni sanab chiqishi mumkin |
| **Yechim** | Shuffling/bijective mapping bilan tartibni aralashtirish |

#### B Yondashuv: Xeshlash (MD5, SHA-256, MurmurHash)

Uzun URLni xeshlash va birinchi N belgini olish.

| Jihat | Tafsilot |
|---|---|
| **Afzalliklari** | Koordinatsiya kerak emas, tabiiy deduplikatsiya, kamroq bashorat qilish mumkin |
| **Kamchiliklari** | **Collisionlar muqarrar** (birthday paradox), collision hal qilish murakkablik qo'shadi |
| **Collision ehtimoli** | ~1M URL bilan 7 belgili qirqilgan xeshlar uchun sezilarli |

**Collision boshqarish strategiyalari:**

1. **Salt bilan qayta urinish:** Collision aniqlansa, kirishga counter/tasodifiy salt qo'shib qayta xeshlash. Muammo: yuqori collision darajasida bir nechta DB so'rovlari
2. **Bloom filter oldindan tekshirish:** Barcha mavjud kodlarning Bloom filtrini saqlash. DB yozishdan oldin a'zolikni tekshirish
3. **Tasodifiy qo'shimcha:** Collision da qisqa kodga tasodifiy belgilar qo'shish
4. **Gibrid yondashuv:** Asosiy yo'l uchun xeshlash, collision da counter-asosidqa tayinlashga o'tish

#### C Yondashuv: Kalit Generatsiya Xizmati (KGS) — Eng Yaxshi

**Ishlab chiqarishda eng ishonchli yondashuv:**

```
1. KGS oldindan millionlab tasodifiy 7 belgili Base62 stringlar yaratadi
   → keys_available jadvalida saqlaydi

2. App serverlar bir partiya kalitlar so'raydi (masalan, 1000 ta)
   → keys_available dan keys_used ga ko'chiriladi

3. Har bir app serverda mahalliy bufer
   → URL yaratish bir zumda (buferdan keyingi kalitni olish)

4. Agar app server ishdan chiqsa
   → ishlatilmagan kalitlar yo'qoladi (3.5T masshtabda qabul qilinadigan)
```

| Jihat | KGS | Counter + Base62 | Xeshlash |
|---|---|---|---|
| **Collision xavfi** | Yo'q | Yo'q | O'rta-Yuqori |
| **Bashorat qilish** | Yo'q (tasodifiy) | Ha (ketma-ket) | Past |
| **Koordinatsiya** | Alohida xizmat | Markaziy counter | Kerak emas |
| **Tezlik** | Juda tez | Tez | O'rtacha (collision bilan) |
| **Tavsiya** | **Katta masshtab** | O'rtacha masshtab | Kichik masshtab |

---

### 3. Ketma-ket vs Tasodifiy Qisqa Kodlar

#### Ketma-ket Kodlar (masalan: aB3, aB4, aB5, ...)

- **Xavfsizlik xavfi:** Oson sanab chiqish mumkin. Hujumchi barcha kodlarni iteratsiya qilib har bir qisqartirilgan URLni topishi mumkin
- **Maxfiylik xavfi:** Tadqiqotchilar goo.gl kabi xizmatlarda milliardlab ketma-ket qisqa URLlarni skanerlash orqali shaxsiy Google Docs, OneDrive fayllari va ro'yxatsiz kontentni topganini namoyish qildi
- **Ma'lumot sizishi:** Yaratilish tartibi, hajmi va o'sish tezligini oshkor qiladi

#### Tasodifiy Kodlar

- **Sanab chiqishga qarshilik:** 7 belgili Base62 kodda ~3.5 trillion mumkin bo'lgan kodlar. Faqat 1 milliard ishlatilsa, tasodifiy taxmin ~0.03% hit darajasiga ega
- Yaratilish vaqti yoki hajmi haqida **ma'lumot sizishi yo'q**

> **Eng yaxshi amaliyot:** Tasodifiy kodlar ishlatish. Sezgir holatlar uchun qo'shimcha autentifikatsiya qatlami qo'shish.

---

### 4. SQL vs NoSQL Ma'lumotlar Bazasi Tanlash

URL shortener ish yukining xususiyatlari:

- **O'qish og'ir:** O'qishlar yozishlardan 100:1 yoki undan ko'p nisbatda ortiq
- **Oddiy kirish namunasi:** Asosiy so'rov bitta kalit qidirish: `SELECT long_url FROM urls WHERE short_code = ?`
- **Yuqori mavjudlik talab:** Ishlamaydigan redirect xizmati internetdagi barcha qisqartirilgan linklar buzilganligini anglatadi
- **Izchillik talabi oddiy:** O'qishlar uchun eventual consistency qabul qilinadigan

| Ma'lumotlar Bazasi | Afzalliklari | Kamchiliklari | Masshtab |
|---|---|---|---|
| **PostgreSQL/MySQL** | ACID, yetuk tooling, kuchli izchillik | Gorizontal masshtablash ehtiyotkorlik talab qiladi | ~100M URLgacha |
| **DynamoDB** | Bir raqamli ms, avtomatik masshtablash, ichki TTL | Katta masshtabda qimmat, standart eventual consistent | Milliardlab URL |
| **Cassandra** | Chiziqli gorizontal masshtablash, yuqori yozish | Operatsion murakkablik, join yo'q | Milliardlab URL |
| **MongoDB** | Moslashuvchan sxema, yaxshi sharding | Sof KV uchun optimal emas | O'rtacha masshtab |

> **Katta masshtab tavsiya:** NoSQL key-value store (DynamoDB/Cassandra) asosiy URL xaritalash uchun + alohida analitika bazasi (ClickHouse, TimescaleDB).

---

## Masshtablash Muammolari

### 1. Milliardlab URLlarni Boshqarish

**Saqlash qatlami:**
- Bitta URL xaritalash yozuvi kichik (~500 bayt)
- 1 milliard URL = ~500 GB — bitta zamonaviy serverga sig'adi, lekin mavjudlik va o'tkazuvchanlik uchun replikatsiya va partitsiyalash kerak
- 10 milliard URLda taqsimlangan saqlash kerak (DynamoDB/Cassandra)

**O'qish o'tkazuvchanligi:**
- 100:1 read:write nisbati va 100M yangi URL/oy (~40 yozish/sek) bilan, ~4,000 o'qish/sek o'rtacha
- Issiq kesh (Redis cluster) o'qishlarning aksariyatini yutadi
- Kesh hit nisbati 80-95% — URL shortenerlar uchun odatiy

### 2. Issiq URL Muammosi (Viral Linklar)

Bitta viral link sekundiga millionlab bosish olishi mumkin — bu klassik "issiq kalit" yoki "issiq partitsiya" muammosi.

**Strategiyalar:**

#### a) Ko'p qatlamli keshlash
```
L1: Application darajali in-memory kesh
    → Har bir server instansiyasi eng issiq URLlarni keshlaydi
    → Nol tarmoq kechikishi

L2: Taqsimlangan kesh (Redis Cluster)
    → Bir nechta tugunlar bo'ylab tarqalgan

L3: CDN edge keshlash
    → 301 redirect ishlatilsa, CDN keshlab, originga murojaat qilmasdan beradi
```

#### b) Issiq kalitlar uchun kesh replikatsiya
- Redis Cluster da issiq kalit bitta shardga tushadi
- **Yechim:** Issiq kalitni tasodifiy qo'shimcha bilan bir nechta shardlar bo'ylab replikatsiya (`shortcode_0`, `shortcode_1`, ..., `shortcode_N`)

#### c) Rate limiting
- Haddan tashqari holatlar uchun qisqa kod boshiga redirectlarni rate-limit qilish

#### d) Asinxron analitika
- Bosish kuzatishni redirect yo'lidan ajratish
- Bosishlarni Kafka topicga yozish va asinxron ishlov berish

### 3. Ma'lumotlar Bazasi Sharding Strategiyalari

| Strategiya | Tavsif | Afzalligi | Kamchiligi |
|---|---|---|---|
| **short_code xeshi** (eng umumiy) | Consistent hashing kodlarni shardlar bo'ylab teng taqsimlaydi | O(1) qidirish, ajoyib balans | - |
| **user_id bo'yicha** | Foydalanuvchiga oid so'rovlar uchun yaxshi | Per-user so'rovlar samarali | Redirect uchun scatter-gather kerak |
| **Yaratilish vaqti bo'yicha** | Vaqt asosida | TTL/tozalash uchun yaxshi | Yangi URL lar issiq shardlar yaratadi |

> **Eng yaxshi amaliyot:** `short_code` bo'yicha consistent hashing. Redirect yo'li aynan bitta shardga murojaat qiladi.

### 4. Global Taqsimlash va Kechikish

Redirect kechikishidagi har bir millisekund foydalanuvchiga seziladi.

**Strategiyalar:**

1. **GeoDNS + Mintaqaviy joylashtirishlar:** Foydalanuvchilarni eng yaqin data markaziga yo'naltirish
2. **CDN-asoslangan redirectlar:** Cloudflare Workers yoki AWS CloudFront Functions 300+ edge lokatsiyada redirect logikasini bajarishi mumkin
3. **Read replikalar:** Har bir mintaqada baza read replikalarini joylashtirish
4. **Edge da keshlash:** CDN 301 redirectlarni keshlash global mashhur URLlar uchun <10ms kechikish beradi

**Redirect uchun kechikish byudjeti:**
```
DNS hal qilish:    0-50ms (keshlangan)
TLS handshake:     0-50ms (ulanish qayta ishlatish)
Server ishlov:     1-5ms (kesh hit) yoki 5-20ms (DB qidirish)
Umumiy maqsad:     < 100ms global
```

### 5. Thundering Herd Muammosi

Mashhur URL ning kesh yozuvi muddati tugaganda, yuzlab/minglab bir vaqtdagi so'rovlar bazaga murojaat qilganda yuzaga keladi.

**Strategiyalar:**

| Strategiya | Tavsif | Afzalligi |
|---|---|---|
| **Singleflight / Request coalescing** | Faqat BITTA so'rov bazaga boradi, boshqalari kutadi | Sodda, samarali |
| **XFetch algoritmi (ehtimollik asosida)** | Muddati tugashidan oldin so'rovlar ehtimollik bilan yangilaydi | Stampede bo'lmasdan oldin kesh yangilanadi |
| **Stale-while-revalidate** | Eskirgan kesh qiymatini darhol berish, fonida yangilash | Foydalanuvchi kechikishini butunlay yo'q qiladi |
| **TTL siz + foniy yangilash** | Eng issiq URLlar uchun TTL o'rnatmasdan, fon yangilash | Hech qachon expire bo'lmaydi |

---

## Dizayn Muammolari

### 1. Maxsus Taxalluslarni Boshqarish

Foydalanuvchilar `qisqa.uz/mening-brendim` kabi vanity URLlar xohlaydi.

**Muammolar:**
- **Mavjudlik tekshiruvi:** Atom bo'lishi kerak — tekshirish va zahiralash bitta tranzaksiyada
  - SQL: `INSERT ... IF NOT EXISTS` yoki unique constraint
  - Cassandra: LWT (Lightweight Transaction)
- **Zahiralangan so'zlar:** `api`, `admin`, `login`, `health`, `static` kabi taxalluslarni bloklash
- **Belgi validatsiya:** `[a-zA-Z0-9\-_]` ruxsat, maxsus belgilar, bo'shliqlar, emoji rad
- **Uzunlik cheklovlari:** Minimum 3-4 belgi, maksimum 30-50 belgi
- **Squatting oldini olish:** Faqat autentifikatsiya/pullik foydalanuvchilarga maxsus taxallus yaratishga ruxsat

### 2. URL Validatsiya va Normalizatsiya

**Validatsiya:**
- URL da to'g'ri sxema borligini tekshirish (`http://` yoki `https://`)
- Hostname hal qilinishini tekshirish (DNS lookup) — ixtiyoriy
- `javascript:`, `data:`, `file:` va boshqa xavfli sxemalarni rad etish
- O'z shorteneringizga qaytadigan URLlarni rad etish (redirect halqalari)
- URL uzunligini tekshirish (max ~2,048 yoki 10,000 belgi)

**Normalizatsiya (deduplikatsiya uchun muhim):**
```
1. Sxema va hostname ni kichik harfga: HTTP://Example.COM/Path → http://example.com/Path
2. Standart portlarni olib tashlash: http://example.com:80/ → http://example.com/
3. Ortiqcha trailing slashlarni olib tashlash (munozarali)
4. Query parametrlarni tartiblash (munozarali)
5. Tracking parametrlarni olib tashlash: utm_source, fbclid (ixtiyoriy)
6. Keraksiz percent-kodlashni dekodlash: %41 → A
7. Fragment identifikatorlarni olib tashlash (#section)
```

### 3. URL Kodlash Edge Case lari

| Holat | Tavsif | Yechim |
|---|---|---|
| **Xalqaro domen nomlari (IDN)** | `example.xn--p1ai` (Punycode) | Unicode va Punycode shakllarini boshqarish |
| **Ikki marta kodlash** | `%2520` (`%20` qayta kodlangan) | Ikki marta dekodlamaslik |
| **Juda uzun URLlar** | Reklama platformalaridan 5,000+ belgi | Limitni belgilash va xabar berish |
| **HTTP-bo'lmagan sxemalar** | `ftp://`, `mailto:`, `tel:` | Qaysilarni qo'llab-quvvatlashni hal qilish |
| **Autentifikatsiyali URLlar** | `https://user:password@example.com` | Xavfsizlik xavfi — olib tashlash yoki rad etishni ko'rib chiqish |

### 4. Link Eskirish va Muddati Tugagan URLlar

- **TTL/Muddati:** Foydalanuvchilarga muddati tugash sanalarini o'rnatishga ruxsat. Muddati tugagan URLlarni belgilash uchun fon jarayoni
- **Javob kodi:** Muddati tugagan URLlar uchun **410 Gone** qaytarish (404 emas) — qidiruv tizimlariga doimiylikni signal berish
- **Standart TTL:** Bepul tarif uchun standart muddati (masalan, 2 yil) — kodlarni qayta tiklash va saqlashni kamaytirish
- **Link rot aniqlash:** Manzil URLlarni davriy tekshirib, hali hal bo'lishini aniqlash. Buzilgan manzillar haqida foydalanuvchilarga xabar berish
- **Tombstoning:** Muddati tugagan qisqa kodlarni darhol qayta ishlatmaslik. Eski linkni xatcho'p qilgan odam uchun chalkashlikni oldini olish uchun tombstone yozuvini saqlash. Qayta ishlatishdan oldin sovutish davrini ko'rib chiqish (masalan, 6 oy)
- **Kod qayta tiklash:** 7 belgili Base62 da 3.5 trillion kod bor — qayta tiklash kerak bo'lmasligi mumkin. 6 belgida (~56 milliard) qayta tiklash oxir-oqibat kerak bo'lishi mumkin

### 5. Suiiste'molni Oldini Olish (Fishing, Zararli Dastur Tarqatish)

Bu URL shortenerlar uchun katta operatsion muammo.

**Himoya qatlamlari:**
```
1. Google Safe Browsing API — har bir yuborilgan URLni tekshirish
2. PhishTank, VirusTotal — qo'shimcha obro' bazalari
3. URL obro' baholash — domen xususiyatlari bo'yicha model
4. Yaratishda rate limiting — anonim uchun IP/vaqt boshiga
5. Oldindan ko'rish sahifalari — belgilangan/ishonchsiz URLlar uchun oraliq ogohlantirish
6. Foydalanuvchi hisobotlari — zararli linklarni xabar berish mexanizmi
7. Avtomatlashtirilgan skanerlash — sandboxda manzil URLni olish va skanerlash
8. Domen bloklist — suiiste'mol qiluvchi domenlarni bloklash
9. Hisob darajasida ta'sir — takroriy zararli link yaratuvchi akkauntlarni o'chirish
```

---

## Ma'lumotlar Modellashtirish

### 1. Asosiy URL Jadvali

```sql
urls
├── short_code (PK)     -- varchar(7), Base62 kod
├── long_url             -- text, manzil URL
├── user_id              -- foreign key yoki anonim uchun null
├── created_at           -- timestamp
├── expires_at           -- timestamp, nullable
├── is_active            -- boolean
├── click_count          -- integer (denormalizatsiya, taxminiy)
└── metadata             -- jsonb (maxsus metadata, teglar, kampaniya)
```

**DynamoDB uchun:**
- Partition key: `short_code`
- Sort key kerak emas
- `user_id` da GSI — per-user ro'yxat uchun

### 2. Bosish Analitikasini Samarali Saqlash

**Muammo:** Kuniga 1 milliard bosish = sekundiga ~12,000 hodisa (cho'qqida 10x ko'proq). Har bir bosishni saqlash qimmat, lekin kuchli.

#### A variant: Raw Hodisa Jurnali (Event Sourcing)

```sql
clicks
├── click_id          -- UUID yoki Snowflake ID
├── short_code        -- bosilgan link
├── timestamp         -- qachon
├── ip_address        -- (maxfiylik uchun xeshlangan)
├── user_agent        -- brauzer/qurilma ma'lumoti
├── referer           -- bosish qayerdan keldi
├── country           -- IP dan GeoIP orqali olingan
├── city              -- IP dan olingan
├── device_type       -- mobil/desktop/planshet
├── os                -- UA dan tahlil qilingan
└── browser           -- UA dan tahlil qilingan
```

- **Afzalliklari:** Maksimal analitik moslashuvchanlik, har qanday savolga javob, retrospektiv tahlil
- **Kamchiliklari:** Katta saqlash. 1B bosish/kun × ~200 bayt = ~200 GB/kun = ~73 TB/yil
- **Eng yaxshi:** Premium analitika mahsuloti, ixtiyoriy so'rovlarga javob kerak bo'lganda
- **Baza:** Columnar store (ClickHouse, Apache Druid, BigQuery) kerak

#### B variant: Oldindan Yig'ilgan Hisoblagichlar

```sql
click_stats_hourly
├── short_code
├── hour_bucket          -- masalan, 2026-04-06T14:00
├── country
├── device_type
├── referer_domain
├── click_count
└── unique_visitors      -- HyperLogLog taxminiy
```

- **Afzalliklari:** Ixcham saqlash, tez dashboard so'rovlari, past kechikish
- **Kamchiliklari:** O'lchovlar oldindan belgilanishi kerak, yangi o'lchovlar backfill talab qiladi
- **Eng yaxshi:** Ma'lum analitika talablari, xarajatga sezgir joylashtirishlar

#### C variant: Lambda Arxitektura (Katta masshtab uchun tavsiya)

Ikkisini birlashtirish:

```
TEZLIK QATLAMI:
  Redis da real-time hisoblagichlar (har bir bosishda increment)
  → Jonli dashboardni quvvatlaydi

BATCH QATLAMI:
  Raw hodisalar Kafka ga → Data warehouse ga (ClickHouse, BigQuery) batch ETL
  → Batafsil analitikani quvvatlaydi

XIZMAT QATLAMI:
  Umumiy so'rovlar uchun oldindan yig'ilgan rolluplar
  (kunlik statistika, mamlakat taqsimotlari)
```

### 3. Vaqt Seriyali Ma'lumotlar Analitika Uchun

Bosish ma'lumotlari tabiatan vaqt seriyali — vaqt seriyasiga optimallashtirilgan tizimlarda eng yaxshi saqlanadi:

| Tizim | Tavsif | Afzalligi |
|---|---|---|
| **ClickHouse** | Ustun-yo'naltirilgan, analitik so'rovlar uchun juda tez | Milliardlab qatorlarni sekundlarda qayta ishlaydi, ochiq manbali |
| **TimescaleDB** | PostgreSQL kengaytmasi | Jamoangiz PG bilsa yaxshi, avtomatik vaqt partitsiyalash |
| **Apache Druid** | Real-time qabul qilish + tarixiy ma'lumot | Sub-sekund OLAP so'rovlari, avtomatik rolluplar |
| **InfluxDB** | Maqsadga mo'ljallangan vaqt seriyali DB | Metrikalar uchun yaxshi, hodisa analitikasi uchun kamroq ideal |

**Partitsiyalash strategiyasi:** Vaqt bo'yicha (kunlik yoki haftalik) asosiy partitsiya + short_code xeshi bo'yicha ikkilamchi partitsiya.

**Saqlash siyosati:** Batafsil ma'lumotlarni 30-90 kun saqlash, kunlik yig'malarga 1-2 yil, oylik yig'malar cheksiz.

### 4. Event Sourcing vs To'g'ridan-to'g'ri Yig'ish

| Jihat | Event Sourcing | To'g'ridan-to'g'ri Yig'ish |
|---|---|---|
| **Yondashuv** | Har bir bosish o'zgarmas hodisa sifatida jurnalanadi | Har bir bosishda hisoblagichlarni to'g'ridan-to'g'ri oshirish |
| **Afzalliklari** | To'liq audit izi, har qanday ko'rinishni qayta qurish, retrospektiv o'lchovlar | Sodda, past o'qish kechikishi, minimal saqlash |
| **Kamchiliklari** | Katta saqlash, replay sekin, murakkablik yuqori | Yo'qotishli — retrospektiv o'lchovlar qo'shib bo'lmaydi |

> **Gibrid (tavsiya):** Raw hodisalarni Kafka ga yozish (event sourcing) VA Redis da real-time hisoblagichlarni yangilash (to'g'ridan-to'g'ri yig'ish). Kafka oqimi batch ishlov uchun barqaror analitik saqlashni ta'minlaydi.

---

## Xavfsizlik Masalalari

### 1. Sanab Chiqish Hujumlarini Oldini Olish

| Himoya | Tavsif |
|---|---|
| **Tasodifiy kodlar** | Kriptografik tasodifiy, ketma-ket emas |
| **Minimum kod uzunligi** | Kamida 6-7 belgi (7 da 3.5T keyspace) |
| **Redirect da rate limiting** | Daqiqada minglab tasodifiy kodlarga so'rov yuboruvchi klientlarni aniqlash va bloklash |
| **Vaqt konstantali javob** | "Kod topilmadi" va "kod topildi" uchun bir xil javob vaqti (timing attack oldini olish) |
| **CAPTCHA** | Shubhali kirish naqshlari uchun yo'naltirishdan oldin challenge |
| **Monitoring** | Ketma-ket kod kirish urinishlari kabi g'ayrioddiy naqshlar haqida ogohlantirish |

### 2. Safe Browsing API Integratsiya

```
YARATISH VAQTIDA:
  → Har bir URLni Google Safe Browsing API v4 ga qarshi tekshirish
  → Ma'lum zararli URLlarni bloklash

DAVRIY QAYTA SKANERLASH:
  → Manzillar yaratilgandan keyin zararli bo'lishi mumkin
  → Barcha faol URLlarni davriy qayta tekshirish (kunlik/haftalik)
  → Yuqori trafikli linklarni ustuvorlik bilan

REDIRECT DA:
  → Ishonchsiz/yangi yaratilgan linklar uchun yo'naltirishdan oldin tekshirish
  → Har bir redirectda API kechikishini oldini olish uchun natijani keshlash

OGOHLANTIRISH SAHIFASI:
  → Manzil belgilanganda, yo'naltirish o'rniga ogohlantirish sahifasi ko'rsatish
```

### 3. Ochiq Redirect Zaifliklarini Oldini Olish

URL shortenerlar **tabiatan ochiq redirectorlar** — bu ularning butun maqsadi. Bu ma'lum ziddiyat.

**Yengillashtirish choralari:**
- **Enterprise uchun manzil domen allowlist:** Faqat oldindan tasdiqlangan domenlarga yo'naltirish
- **Ogohlantirish oraliq sahifasi:** Past obro'li domenlarga olib boradigan linklar uchun
- **OAuth oqimlarida suiiste'molga yo'l qo'ymaslik:** Shorteneringiz autentifikatsiya redirect endpointi sifatida ishlatilmasligini ta'minlash
- **`rel="noopener noreferrer"`:** HTML kontekstlarida linklar render qilinganda referrer sizishini oldini olish

### 4. Input Validatsiya va Sanitizatsiya

| Himoya | Tafsilot |
|---|---|
| **URL sxema allowlist** | Faqat `http` va `https`. `javascript:`, `data:`, `file:` rad etish |
| **URL tahlil** | Ishonchli URL parser ishlatish (regex emas) |
| **Maksimum URL uzunligi** | Limit o'rnatish (masalan, 2,048 yoki 10,000 belgi) |
| **XSS oldini olish** | URLlarni ko'rsatishda HTML-escape qilish |
| **SQL injection** | Faqat parametrlangan so'rovlar, hech qachon URL concatenation |
| **Header injection** | `Location` headeri `\r\n` (CRLF injection) o'z ichiga olmasligi kerak |

---

## Sig'im Hisoblash

### Taxminlar: 100M yangi URL/oy, 10:1 read:write nisbati

#### Yozish QPS (URL Yaratish)

```
100M URL / oy
= 100,000,000 / (30 × 24 × 3600)
= 100,000,000 / 2,592,000
≈ 38.6 yozish/sekund (o'rtacha)

Cho'qqi (5x o'rtacha):
≈ 193 yozish/sekund
```

> Bu juda boshqarish oson. Bitta PostgreSQL instansiyasi buni osongina bajaradi.

#### O'qish QPS (Redirectlar)

```
10:1 read:write nisbat
= 38.6 × 10 = 386 o'qish/sekund (o'rtacha)

Cho'qqi (5x o'rtacha):
≈ 1,930 o'qish/sekund

Viral spike bilan (100x o'rtacha):
≈ 38,600 o'qish/sekund
```

> Keshlash bilan (90% hit nisbati) baza faqat ~39 o'qish/sekund ko'radi — ahamiyatsiz.

#### Saqlash Hisoblash

**URL saqlash (har bir yozuv):**
```
short_code:    7 bayt
long_url:      ~100 bayt o'rtacha
user_id:       8 bayt (bigint)
created_at:    8 bayt
expires_at:    8 bayt
is_active:     1 bayt
metadata:      ~50 bayt o'rtacha
DB overhead:   ~50 bayt (indekslar, qator headerlari)
─────────────────────
Jami URL boshiga: ~232 bayt, indekslar bilan ~500 baytga yaxlitlash
```

```
100M URL/oy:
  Har oy:    100M × 500 bayt = 50 GB
  Har yil:   600 GB
  5 yil:     3 TB
```

**Bosish analitika saqlash (raw hodisalar):**
```
Oyiga bosishlar:  100M × 10 = 1B bosish/oy
Har bir hodisa:   ~200 bayt

Har oy:   1B × 200 bayt = 200 GB
Har yil:  2.4 TB
5 yil:    12 TB
```

> ClickHouse odatda 10:1 siqish nisbatiga erishadi, shuning uchun 12 TB raw diskda ~1.2 TB bo'ladi.

#### Bandwidth Hisoblash

```
Kiruvchi (yozish):
  38.6 yozish/sek × 500 bayt = ~19 KB/s (ahamiyatsiz)

Chiquvchi (redirect):
  Har bir redirect javobi: ~500 bayt (HTTP headerlar + Location header)
  386 o'qish/sek × 500 bayt = ~193 KB/s o'rtacha
  Cho'qqi: ~9.65 MB/s
```

> Bandwidth to'siq emas.

#### Kesh Hajmi Hisoblash

```
Pareto printsipi (80/20 qoidasi):
  20% URLlar 80% trafikni yaratadi

Kunlik faol URLlar:
  Barcha URLlarning 10% ga kunlik kirish (1 yildan keyin 1.2B jami = 10M URL)

Kunlik faol URLlarning 20% ini keshlash:
  = 2M URL

Kesh xotirasi:
  2M × 500 bayt = 1 GB

Keng zaxira bilan: 5-10 GB Redis instansiya
```

> Bitta Redis instansiyasiga oson sig'adi.

#### Turli Masshtablarda Xulosa

| Metrika | 100M URL/oy | 1B URL/oy | 10B URL/oy |
|---|---|---|---|
| Yozish QPS (o'rtacha) | ~39 | ~390 | ~3,900 |
| O'qish QPS (o'rtacha) | ~390 | ~3,900 | ~39,000 |
| O'qish QPS (cho'qqi) | ~2K | ~20K | ~200K |
| URL saqlash/yil | 600 GB | 6 TB | 60 TB |
| Bosish saqlash/yil | 2.4 TB | 24 TB | 240 TB |
| Kesh hajmi | 5-10 GB | 50-100 GB | 500 GB - 1 TB |
| DB tanlovi | PostgreSQL + replikalar | DynamoDB/Cassandra cluster | DynamoDB/Cassandra + aggressiv keshlash |
| Redis | Bitta instansiya | Cluster (3-6 tugun) | Katta cluster (10+ tugun) |
| App serverlar | 2-3 | 10-20 | 50-100+ |
