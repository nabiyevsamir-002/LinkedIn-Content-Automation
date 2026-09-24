---
title: "Microsoft kütləvi hack platformasını dayandırdı — 12,000 hesab kompromis edildi"
date: 2026-09-23T12:08:25.127715+04:00
pillar: research
linkedin: https://www.linkedin.com/feed/update/urn:li:share:7508437100455927809/
source: https://arstechnica.com/security/2026/09/microsoft-disrupts-ai-assisted-platform-that-compromised-12000/
scores: {'hook': 6, 'concreteness': 8, 'local_relevance': 2, 'voice': 5, 'overall': 6}
queue_id: 2026-09-23T05-13-28
---

# Microsoft kütləvi hack platformasını dayandırdı — 12,000 hesab kompromis edildi

*bu gün 12:08 · Bakı vaxtı*

## Post

12,000-dən çox Microsoft hesabı kompromise oldu. 10,000-dən çox təşkilat təsirləndi. Platforma təxminən yeddi ay (fevraldan sentyabra qədər) heç kimin gözünə dəymədi.

Amma qurbanlar saxta login səhifəsinə düşmədi. Onlar Microsoft-un öz rəsmi ekranında kod daxil etdilər. Bu, OAuth device-code axını üzərindən baş verdi.

AI burada mətn yazmadı, inandırıcı e-poçt qurmadı. O, artıq kompromise olunmuş poçt qutularını analiz edib kimin fakturanı ödəyəcəyini, kimə pul köçürüləcəyini müəyyənləşdirdi.

Yəni giriş nöqtəsi model deyildi. Protokolun özü idi. Parol tələb etməyən bir axın, ənənəvi phishing filtrlərinin heç birini işə salmadı.

Microsoft bunu "AI ilə işləyən phishing platforması" adlandırdı. Bu başlıq diqqəti səhv obyektə yönəldir. Sual modeldən çox, hansı autentifikasiya axınının parolsuz və izsiz qaldığıdır.

Developer kimi işlətdiyiniz hər device-code login (CLI, TV app, IoT) bu baxımdan yenidən nəzərdən keçirilməyə dəyər.

Sizin sistemlərinizdə device-code axınını kim audit edir?

#AI #Cybersecurity #OAuth #DevSecOps

## Birinci şərh

Mənbə: Microsoft-un rəsmi açıqlaması — https://blogs.microsoft.com/on-the-issues/2026/09/22/disrupting-eviltokens-the-ai-chatbot-built-for-cybercrime/

## Şəkil

`/Users/samirnbiyev/Projects/Avto-post Linkedin/state/images/2026-09-23T05-13-28.png`

> Qaranlıq otaqda kompüter ekranı qarşısında oturan naməlum şəxsin kiberhücum və hakerlik atmosferini əks etdirən şəkli; fonda kod sətirləri və təhlükəsizlik xəbərdarlığı rəngləri.

## Faktlar

- [high] Microsoft EvilTokens adlı AI-dəstəkli phishing-as-a-service platformasının infrastrukturunu dağıtdığını 22 sentyabr 2026-cı ildə rəsmi bloqunda açıqladı.
- [high] Platforma OAuth cihaz kodu (device code) autentifikasiyasını kütləvi miqyasda sui-istifadə edən ilk PhaaS xidməti idi və fevral ayında ortaya çıxdı.
- [high] Platforma 10,000-dən çox təşkilatda 12,000-dən artıq Microsoft hesabını kompromise etdi, əsasən ABŞ-da.
- [medium] Xidmət Telegram üzərindən satılırdı; qeydiyyat ödənişi $1,500 (birdəfəlik) + $500 aylıq abunə idi.
- [medium] London Metropolitan Polisi 11 sentyabr 2026-cı ildə 32 və 38 yaşlı iki şəxsi platformanın idarə edilməsi şübhəsi ilə həbs etdi.
- [medium] SpyCloud əməkdaşlıq çərçivəsində 79 ölkədə 6,585 korporativ domendə 8,708 unikal qurban hesabını bərpa etdi.
- [medium] Coinbase tərəfindən izlənilən oktyabr 2025 - iyun 2026 aralığında platformanın gəliri 1,1 milyon dollar olaraq qiymətləndirildi, 700-dən çox unikal kripto ünvandan 1,000-dən çox depozit vasitəsilə.
- [medium] Microsoft, Health-ISAC və hüquq-mühafizə orqanları ilə birlikdə 50 sayt müsadirə etdi və 150-dən çox domeni deaktiv etdi.
- [high] Platformanın AI alətləri kompromise olunmuş poçt qutularını analiz edərək fakturaları, pul köçürmə danışıqlarını müəyyənləşdirir və hücumçulara kimi təqlid edəcəklərini tövsiyə edirdi.
- **Kompromise olunmuş Microsoft hesabları**: 12,000+
- **Təsirlənmiş təşkilatların sayı**: 10,000+
- **Müsadirə olunmuş saytlar**: 50
- **Deaktiv edilmiş domenlər**: 150+
- **Platforma gəliri (Coinbase izləməsi, okt 2025-iyun 2026)**: $1.1 milyon
- **Office 365 capture link qiyməti**: $1,500 birdəfəlik + $500/ay
- **Həbs olunanların sayı**: 2 nəfər (32 və 38 yaş)
- **SpyCloud tərəfindən bərpa edilən qurban hesabları**: 8,708 unikal hesab / 6,585 domen / 79 ölkə

İlkin mənbə: https://blogs.microsoft.com/on-the-issues/2026/09/22/disrupting-eviltokens-the-ai-chatbot-built-for-cybercrime/
