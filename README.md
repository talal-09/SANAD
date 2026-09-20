# سَنَد | SANAD

[![Tests](https://github.com/talal-09/SANAD/actions/workflows/tests.yml/badge.svg)](https://github.com/talal-09/SANAD/actions/workflows/tests.yml)

سَنَد نموذج أولي عربي يساعد طبيب الأشعة على مراجعة العقد الرئوية المحتملة في صور CT، وتصحيح موضعها وقياسها، ثم متابعة الحالة ضمن مسار عمل واضح.

> مشروع بحثي وتجريبي للعرض. لا يُستخدم للتشخيص أو لاتخاذ قرار علاجي مستقل، والقرار النهائي للطبيب.

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

يوجد حاليًا 66 اختبارًا تغطي الصلاحيات، عزل بيانات المنشآت، رفع الملفات، مراجعة نتائج النموذج، التنبيهات، وحالات الخطأ.

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
