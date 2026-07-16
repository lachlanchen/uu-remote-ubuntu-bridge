<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# جسر UU Remote لنظام Ubuntu

**اعرض سطح مكتب Ubuntu GNOME وتحكّم فيه بالكامل بواسطة NetEase UU Remote.**

</div>

<div dir="rtl">

هذا مشروع تجريبي يشغّل عميل UU الرسمي لنظام Windows داخل Wine، ثم ينقل سطح
مكتب GNOME Wayland الحقيقي عبر اتصال RDP محلي. يدعم العرض والفأرة ولوحة
المفاتيح وإعادة التشغيل التلقائي.

الإصدار الحالي مقيد عمداً بـ UU Remote `4.33.0.8907` على Ubuntu 24.04 وGNOME
46 وWine 11. لا يُطبّق المشروع أي تعديل على ملف غير معروف.

## التثبيت السريع

</div>

```bash
./install.sh
```

<div dir="rtl">

يثبّت البرنامج النصي الاعتماديات، وينزّل الملفات ذات البصمات المعتمدة، ويبني
مكوّنات التوافق، ويضبط GNOME Remote Desktop، ويحفظ كلمة مرور RDP في GNOME
Keyring، ثم يشغّل خدمة systemd للمستخدم. يمكن تشغيله مراراً بأمان.

## مسار الاتصال

</div>

```text
UU controller -> UU in Wine -> input broker -> SDL FreeRDP
              -> GNOME Remote Desktop -> GNOME Wayland desktop
```

<div dir="rtl">

## عند صدور تحديث جديد

لا يقوم المشروع بترقيع إصدار جديد تلقائياً. تقوم الأدوات بجمع أقسام PE،
والسلاسل الدلالية، والمرشحين، ومقاطع `objdump`، ثم تنشئ مسودة غير قابلة
للتنفيذ. لا تصبح المسودة بياناً معتمداً إلا بعد مراجعة التفكيك واختبار نسخة
مؤقتة.

- [طريقة الصيانة الكاملة](../docs/upstream-maintenance.md)
- [المنهجية والأدوات](../docs/methodology-and-toolkit.md)
- [سجل الهندسة العكسية](../docs/reverse-engineering.md)
- [الأمان](../docs/security.md)
- [استكشاف الأخطاء](../docs/troubleshooting.md)

لا يحتوي المستودع على كلمات مرور أو رموز حساب أو معرفات أجهزة أو ملفات UU
التنفيذية أو سجلات خاصة. المشروع جزء من
[The Art of Lazying](https://lazying.art).

> المرجع التقني الكامل مكتوب بالإنجليزية لتبقى الأوامر والبصمات والبايتات
> متطابقة في مصدر واحد.

</div>
