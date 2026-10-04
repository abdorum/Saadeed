# مسودات للتجربة

| الملف | المصدر | الغرض |
|---|---|---|
| `demo_khutbah.txt` | صاغها Claude (4 أكتوبر 2026) | مسودة العرض: خمسة عيوب مزروعة **عمدًا** (آية محرّفة، وحديث مشتهر لا يصح، وإجماع مدّعى، وقول منسوب بلا مصدر، واستنتاج يتجاوز لفظ الحديث، ورقم بلا مصدر) |
| `alukah_hifz_allisan.txt` | مقتطف من «خطبة عن الحث على حفظ اللسان»، أ. عبدالعزيز بن أحمد الغامدي، شبكة الألوكة (2016): https://www.alukah.net/alaqeel/1/100556/ | خطبة حقيقية منشورة، تُستعمل مثالًا للتتبع في `docs/core-guide.md`. حقوقها لصاحبها وللألوكة، والمقتطف للتحليل مع النسبة |

```bash
uv run saadeed review samples/alukah_hifz_allisan.txt
uv run saadeed review samples/demo_khutbah.txt --overreach
```
