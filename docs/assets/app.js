(() => {
  const navToggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.site-nav');
  navToggle?.addEventListener('click', () => {
    const open = nav.classList.toggle('open');
    navToggle.setAttribute('aria-expanded', String(open));
  });
  nav?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => {
    nav.classList.remove('open');
    navToggle?.setAttribute('aria-expanded', 'false');
  }));

  const steps = [
    { label: 'الخطوة الأولى', title: 'ابدأ بالمريض', description: 'يعرض سَنَد بيانات الحالة الأساسية فقط، ويقيد الوصول بحسب منشأة المستخدم وصلاحياته.', points: ['رقم حالة تجريبي', 'سجل واضح ومختصر', 'صلاحيات حسب الدور والمنشأة'], view: 'patient', record: 'حالة تجريبية 001', status: 'بانتظار رفع الأشعة' },
    { label: 'الخطوة الثانية', title: 'ارفع دراسة CT', description: 'يتحقق النظام من ملف ZIP ومحتوى DICOM قبل حفظ الدراسة في مساحة خاصة غير عامة.', points: ['منع الملفات التنفيذية', 'فحص اتساق الدراسة', 'حدود للحجم ونسبة الضغط'], view: 'scan', record: 'دراسة صدر CT', status: 'تم التحقق من الملفات' },
    { label: 'الخطوة الثالثة', title: 'ابدأ التحليل', description: 'يشغل سَنَد نموذج MONAI في عملية معزولة ويحوّل المخرجات إلى مواضع قابلة للمراجعة.', points: ['تحليل ثلاثي الأبعاد', 'نتائج أولية غير معتمدة', 'تتبع حالة المهمة'], view: 'analysis', record: 'تحليل النموذج', status: 'اكتملت المعالجة' },
    { label: 'الخطوة الرابعة', title: 'ثبّت قرار الطبيب', description: 'يراجع الطبيب كل موضع، ويحرك علامة القياس عند الحاجة قبل اعتماد القرار.', points: ['قبول أو تصحيح أو رفض', 'حفظ الإحداثيات المصححة', 'توثيق المراجع والوقت'], view: 'decision', record: 'موضع محتمل 9.4 مم', status: 'بانتظار قرار الطبيب' },
    { label: 'الخطوة الخامسة', title: 'تابع الحالة', description: 'ينشئ سَنَد خطة المتابعة والتنبيهات المستحقة تلقائيًا وفق قرار الطبيب.', points: ['موعد متابعة واضح', 'تنبيهات تلقائية', 'سجل حالة قابل للتتبع'], view: 'followup', record: 'متابعة بعد 3 أشهر', status: 'الخطة جاهزة' }
  ];

  const tabs = [...document.querySelectorAll('.demo-steps button')];
  const panel = document.querySelector('#demo-panel');
  const label = document.querySelector('#demo-label');
  const title = document.querySelector('#demo-title');
  const description = document.querySelector('#demo-description');
  const points = document.querySelector('#demo-points');
  const visual = document.querySelector('#demo-visual');
  const recordTitle = visual?.querySelector('.demo-record strong');
  const recordStatus = visual?.querySelector('.demo-record small');
  const next = document.querySelector('.demo-next');
  let active = 0;

  function setStep(index, focus = false) {
    active = (index + steps.length) % steps.length;
    const step = steps[active];
    tabs.forEach((tab, tabIndex) => {
      const selected = tabIndex === active;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    label.textContent = step.label;
    title.textContent = step.title;
    description.textContent = step.description;
    points.replaceChildren(...step.points.map((text) => {
      const item = document.createElement('li');
      item.textContent = text;
      return item;
    }));
    visual.dataset.view = step.view;
    recordTitle.textContent = step.record;
    recordStatus.textContent = step.status;
    next.textContent = active === steps.length - 1 ? 'العودة للبداية' : 'الخطوة التالية';
    if (focus) tabs[active].focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setStep(index));
    tab.addEventListener('keydown', (event) => {
      if (event.key === 'ArrowLeft') { event.preventDefault(); setStep(active + 1, true); }
      if (event.key === 'ArrowRight') { event.preventDefault(); setStep(active - 1, true); }
    });
  });
  next?.addEventListener('click', () => setStep(active + 1));

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const reveals = document.querySelectorAll('.reveal');
  if (reducedMotion || !('IntersectionObserver' in window)) {
    reveals.forEach((element) => element.classList.add('visible'));
  } else {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12 });
    reveals.forEach((element) => observer.observe(element));
  }

  document.querySelector('#year').textContent = new Date().getFullYear();
  panel?.setAttribute('aria-labelledby', 'demo-title');
})();
