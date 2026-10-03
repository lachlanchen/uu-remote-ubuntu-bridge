<div align="center">

[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

# جسر UU Remote لنظام Ubuntu

**اعرض سطح مكتب Ubuntu GNOME وتحكّم فيه بالكامل بواسطة NetEase UU Remote.**

<p>
  <a href="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp">
    <img src="../docs/images/uu-remote-ubuntu-desktop-from-macos.webp" alt="سطح مكتب Ubuntu GNOME يتم الوصول إليه من macOS عبر UU Remote Ubuntu Bridge." width="1120">
  </a>
  <br>
  <sub>سطح مكتب Ubuntu GNOME يتم الوصول إليه من macOS عبر UU Remote Ubuntu Bridge.</sub>
</p>

</div>

<div dir="rtl">

يشغّل هذا الجسر التجريبي عميل Windows الرسمي داخل بادئة Wine معزولة، ويشارك
سطح مكتب GNOME الحالي عبر RDP محلي أو مرحّل VNC محلي اختياري لجلسات X11.

البيئة الأساسية هي Ubuntu 24.04 بمعمارية x86-64 وGNOME 46 وWine 11. تبقى
التثبيتات الجديدة مثبتة على UU `4.33.0.8907`؛ وللإصدار `4.42.1.2835` بيان
منفصل بقيم تجزئة دقيقة وسجلات قبول خاصة به. لا تُعدّل الملفات الثنائية المجهولة.

<!-- feature-status:start -->
## الميزات التي تعمل

تاريخ المراجعة: **2026-10-04**. يعمل التحكم بسطح المكتب وحافظة النص والإملاء
عبر المسارات التي اختُبرت أو أكد المستخدم نجاحها. لا يعني ذلك ضمان جميع
الأجهزة أو تخطيطات لوحة المفاتيح أو ميزات عميل UU الأصلي على Windows.

| الميزة | الحالة | النطاق والقيود |
| --- | --- | --- |
| سطح مكتب Ubuntu الحالي | تعمل | يحافظ العرض وإعادة الاتصال على الجلسة المختارة والتطبيقات المفتوحة. |
| الفأرة | تعمل | الحركة والنقر والأزرار والعجلة والتركيز عبر المسارات المختبرة. |
| لوحة المفاتيح الفعلية والاختصارات | تعمل حسب العميل | الحروف ومفاتيح التعديل والرموز؛ لا ضمان شامل لكل تخطيطات US وJIS وMac. |
| لوحة الهاتف وUnicode | تعمل عبر المسارات المختبرة | الصينية وعلامات الترقيم والرموز التعبيرية والنص متعدد الأسطر؛ يلزم فحص كل IME. |
| الإملاء المستمر | مؤكد في الاستخدام مع اختبارات انحدار | تحافظ مراجعات الإدخال على الرسائل السابقة؛ يختلف نطاق اختبار الهواتف الفعلية حسب الإصدار. |
| حافظة النص في الاتجاهين | تعمل حسب المسار | نص فقط. مسار الإرجاع X11/VNC اختياري بحد 60 KiB؛ لا يشمل الصور أو الملفات. |
| سطح مكتب واحد عبر UU وRDP وRealVNC | إعداد اختياري | خلفية X11 فعلية مشتركة؛ لا تُدمج الجلسات الافتراضية المنفصلة تلقائياً. |
| الدقة وملاءمة مساحة العرض | قابلة للضبط | حجم ثابت أو متابعة اختيارية لحجم X11/VNC المستقر؛ ليست شاشات افتراضية إضافية. |
| الاستعادة والتشغيل عند الإقلاع | مشروطة | إعادة تشغيل مراقبة مع حفظ تسجيل الدخول؛ تتطلب جلسة GNOME وحافظة مفاتيح قابلتين للاستخدام. لم تتضمن مراجعة 4.42 إعادة اختبار إقلاع الجهاز. |
| طرفية UU الأصلية إلى صدفة Ubuntu | المحول يعمل، والقناة مشروطة | UTF-8 وتغيير حجم PTY؛ تبقى قيود إصدار المورّد والاتصال ورمز الخروج الأصلي. |
| `uu-shell` | متحقق منه عبر SSH المسجل | اختيار صريح بين LazyTunnel وSSH المحوّل والطرفية الأصلية؛ نجاح SSH لا يثبت نجاح قناة UU الأصلية. |
| تحويل منافذ UU وSSH وSCP | مشروطة | توجد مسارات ناجحة؛ قد تنقطع عند الاستحواذ على التحكم أو إغلاق الاتصال الحامل. ليست VPN. |
| Super Screen والشاشات الافتراضية الإضافية | غير متحقق منها | لا اختبار قبول مثبت لجسر Ubuntu؛ تغيير حجم سطح المكتب العادي ليس دليلاً. |
| منع التلصص وشاشة الخصوصية | غير متحقق منها | لا خلفية Linux مثبتة لإخفاء الشاشة الفعلية وقفل الإدخال المحلي. لا تعتمد عليها لحماية الخصوصية. |
| الصوت والميكروفون | محدودة | تعتمد على المضيف؛ تستخدم بعض التثبيتات خلفية صامتة عمداً. |
| نقل الملفات الأصلي وحافظة الصور والملفات والميزات الأخرى | غير متحقق منها | نسخ النص ليس نقل ملفات؛ SCP/SFTP عبر SSH متحقق منه خيار مستقل. |

راجع [الأدلة والقيود](../docs/features.md) وسجلي القبول المنفصلين
لـ [RDP](../docs/releases/4.42.1.2835-acceptance.md) و
[X11](../docs/releases/4.42-x11-workstation-20261001.md). لم يختبر تشغيل عميل Mac
للإصدار 4.42 الإملاء المستمر من هاتف فعلي. كما توجد مشكلة موثقة مع الرموز التعبيرية
خارج BMP في حافظة سطح المكتب المشترك عبر XRDP 0.9.24.

لجهاز سبق إعداده باسم `lab`:

```bash
uu-shell --list
uu-shell lab
uu-shell --lazy lab hostname
uu-shell --native lab
```

استبدل `lab` باسم ملف جهازك. يتطلب `--lazy` التسجيل في LazyTunnel؛ ويطلب
`--native` طرفية UU نفسها، وقد يفشل بشكل مستقل. لا تبديل خفي للمسار ولا استحواذ
على سطح المكتب. [التفاصيل](../docs/fleet-shell.md).
<!-- feature-status:end -->

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
- [طرفية Ubuntu الأصلية](../docs/native-ubuntu-terminal.md)
- [أسماء SSH المختصرة وتعيين المنافذ بين جهازين](../docs/ssh-and-port-mapping.md)

لا يحتوي المستودع على كلمات مرور أو رموز حساب أو معرفات أجهزة أو ملفات UU
التنفيذية أو سجلات خاصة. المشروع جزء من
[The Art of Lazying](https://lazying.art).

إذا كنت تحتاج إلى مسار مستقل عن المورّد، فإن [LazyRemote](https://remote.lazying.art/?utm_source=github&utm_medium=readme&utm_campaign=uu_remote_bridge&utm_content=independent_option_ar#review) يستخدم نواة [LazyTunnel](https://github.com/lachlanchen/LazyTunnel) المفتوحة المصدر والمنفصلة للوصول الذاتي الاستضافة عبر SSH والطرفية وnoVNC. إنها أداة مختلفة؛ ويبقى هذا المستودع مسار التوافق مع عميل UU الرسمي.

## دعم المشروع

إذا وفّر عليك هذا الجسر وقتاً، يمكنك دعم استمرار صيانة التوافق:

| GitHub Sponsors | LazyingArt Donate | PayPal | Stripe |
| --- | --- | --- | --- |
| [![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsor-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen) | [![Donate](https://img.shields.io/badge/LazyingArt-Donate-0EA5E9?style=for-the-badge&logo=ko-fi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-Donate-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |

> المرجع التقني الكامل مكتوب بالإنجليزية لتبقى الأوامر والبصمات والبايتات
> متطابقة في مصدر واحد.

</div>
