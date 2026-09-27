# سَنَد | SANAD

[![الاختبارات](https://github.com/talal-09/SANAD/actions/workflows/tests.yml/badge.svg)](https://github.com/talal-09/SANAD/actions/workflows/tests.yml)

[English](README.md) · **العربية**

**[استعرض سَنَد مباشرة](https://talal-09.github.io/SANAD/)**

سَنَد نموذج أولي عربي يساعد طبيب الأشعة على مراجعة العقد الرئوية المحتملة في صور CT، وتصحيح موضعها وقياسها، ثم متابعة الحالة ضمن مسار عمل واضح.

> مشروع بحثي وتجريبي للعرض. لا يُستخدم للتشخيص أو لاتخاذ قرار علاجي مستقل، والقرار النهائي للطبيب.

## معاينة المشروع

<p align="center">
  <img src="docs/assets/sanad-overview.svg" alt="معاينة واجهة سَنَد لمراجعة موضع محتمل في صورة أشعة مقطعية" width="100%">
</p>

<p align="center">
  <img src="docs/assets/sanad-workflow.svg" alt="معاينة مسار الطبيب في سَنَد من تسجيل الحالة إلى المتابعة" width="100%">
</p>

> الصور معاينات توضيحية مبنية على واجهة العرض، وتستخدم بيانات اصطناعية فقط.

## ماذا يقدم؟

1. تسجيل المريض وربطه بالمنشأة الصحية.
2. رفع دراسة CT محمية.
3. تشغيل نموذج MONAI لاكتشاف المواضع المحتملة.
4. مراجعة الطبيب لكل موضع: قبول، تصحيح، أو رفض.
5. إنشاء المتابعة والتنبيهات تلقائيًا.

## التقنيات

- Django 6.1
- MONAI وPyTorch
- pydicom لمعالجة DICOM
- SQLite للتجربة المحلية
- واجهة عربية متجاوبة
- تخزين Cloudinary خاص واختياري

## تشغيل الواجهة محليًا

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver
```

افتح `http://127.0.0.1:8000/`.

## ربط Cloudinary

يحفظ سَنَد ملفات DICOM وتقارير PDF محليًا افتراضيًا. لتفعيل Cloudinary، انسخ قيمة **API Environment variable** من لوحة Cloudinary إلى ملف `.env` المحلي:

```dotenv
CLOUDINARY_URL=cloudinary://api_key:api_secret@cloud_name?secure=true
SANAD_CLOUDINARY_ENABLED=1
SANAD_CLOUDINARY_FOLDER=sanad/private-medical
```

ثم أعد تشغيل الخادم. تُرفع الملفات الجديدة كأصول `raw/authenticated` ولا يوفّر التطبيق لها رابطًا عامًا. ينزّل التطبيق نسخة مؤقتة محمية إلى `private_uploads/cloudinary_cache` فقط عندما يحتاج تحليل DICOM إلى مسار محلي. ملفات الرفع القديمة لا تُنقل تلقائيًا.

تحقق من بيانات الاتصال دون رفع أي ملف:

```powershell
python manage.py check_cloudinary
```

> بيانات الأشعة معلومات صحية حساسة. لا تستخدم حساب Cloudinary فعليًا لبيانات مرضى قبل التحقق من متطلبات الإقامة الجغرافية، اتفاقية معالجة البيانات، ومتطلبات الجهة التنظيمية أو اتفاقية BAA المناسبة لحالتك.

## تشغيل الذكاء الاصطناعي

بيئة الذكاء الاصطناعي منفصلة بسبب حجم PyTorch وMONAI. ثبّت إصدار PyTorch المناسب لكرت الشاشة، ثم:

```powershell
python -m venv .venv-ai
.\.venv-ai\Scripts\Activate.ps1
python -m pip install -r requirements-ai.txt
```

أوزان النموذج غير محفوظة في Git. ضع النموذج المعتمد في:

```text
ai_models/lung_nodule_ct_detection/models/model.pt
```

يمكن تغيير المسارات بواسطة `SANAD_AI_PYTHON` و`SANAD_AI_MODEL_ROOT`.

## الاختبارات

```powershell
python manage.py test
python manage.py check --deploy
```

تتضمن الحزمة الحالية 74 اختبارًا آليًا تغطي الصلاحيات، عزل بيانات المنشآت، رفع الملفات، التخزين السحابي الخاص، مراجعة نتائج النموذج، التنبيهات، وحالات الخطأ.

## نتائج النموذج

راجع [MODEL_CARD.md](MODEL_CARD.md) للنتائج والقيود. على مجموعة اختبار LUNA16 المنفصلة، اكتشف النموذج 97 من 102 عقدة، مع 2.51 إنذار خاطئ لكل دراسة. هذه نتيجة بحثية وليست اعتمادًا سريريًا.

## الخصوصية والأمان

- لا يتضمن المستودع بيانات مرضى أو صور DICOM أو قاعدة البيانات المحلية.
- الملفات الطبية تحفظ خارج مجلد الوسائط العام وتخضع لصلاحيات المنشأة.
- توجد حماية CSRF وCSP وحدود لملفات ZIP ومحاولات تسجيل الدخول.
- راجع [SECURITY_AUDIT.md](SECURITY_AUDIT.md) و[SECURITY.md](SECURITY.md).

## البيانات والاعتمادات

يعتمد نموذج الكشف على حزمة MONAI وبيانات LUNA16 المبنية على LIDC-IDRI. يجب الالتزام بشروط البيانات وذكر أصحابها. توجد تفاصيل الترخيص والمراجع في `ai_models/lung_nodule_ct_detection/docs`.

## الترخيص

كود سَنَد متاح بموجب ترخيص [Apache License 2.0](LICENSE). تحتفظ المكونات الخارجية وبيانات التدريب بتراخيصها وشروط استخدامها الموجودة داخل مجلداتها ومصادرها الأصلية.
