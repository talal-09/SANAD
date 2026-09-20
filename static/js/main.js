(() => {
  "use strict";

  const ready = (callback) => document.readyState === "loading"
    ? document.addEventListener("DOMContentLoaded", callback, { once: true })
    : callback();

  ready(() => {
    const button = document.querySelector(".menu-button");
    const nav = document.querySelector(".main-nav");
    const backdrop = document.querySelector(".sidebar-backdrop");

    const closeMenu = () => {
      if (!button || !nav) return;
      nav.classList.remove("open");
      document.body.classList.remove("nav-open");
      if (backdrop) {
        backdrop.setAttribute("aria-hidden", "true");
        backdrop.setAttribute("tabindex", "-1");
      }
      button.setAttribute("aria-expanded", "false");
      button.setAttribute("aria-label", "فتح القائمة");
    };

    const openMenu = () => {
      if (!button || !nav) return;
      nav.classList.add("open");
      document.body.classList.add("nav-open");
      if (backdrop) {
        backdrop.setAttribute("aria-hidden", "false");
        backdrop.setAttribute("tabindex", "0");
      }
      button.setAttribute("aria-expanded", "true");
      button.setAttribute("aria-label", "إغلاق القائمة");
    };

    if (button && nav) {
      button.addEventListener("click", () => nav.classList.contains("open") ? closeMenu() : openMenu());
      nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
      if (backdrop) backdrop.addEventListener("click", closeMenu);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && nav.classList.contains("open")) {
          closeMenu();
          button.focus();
        }
      });
      window.addEventListener("resize", () => {
        if (window.innerWidth > 900) closeMenu();
      });
    }

    document.querySelectorAll('input[type="file"]').forEach((input) => {
      const status = document.createElement("p");
      status.className = "file-status";
      status.setAttribute("aria-live", "polite");
      status.textContent = "لم يتم اختيار ملف.";
      input.insertAdjacentElement("afterend", status);
      input.addEventListener("change", () => {
        const file = input.files && input.files[0];
        status.textContent = file
          ? `الملف المختار: ${file.name} — ${(file.size / 1024 / 1024).toFixed(1)} ميجابايت`
          : "لم يتم اختيار ملف.";
      });
    });

    document.querySelectorAll("form").forEach((form) => {
      form.addEventListener("submit", () => {
        const submit = form.querySelector('button[type="submit"]');
        if (!submit || form.classList.contains("logout-form")) return;
        submit.disabled = true;
        submit.setAttribute("aria-busy", "true");
        submit.classList.add("is-loading");
        submit.textContent = "جارٍ التنفيذ…";
      });
    });

    document.querySelectorAll(".message:not(.error)").forEach((message) => {
      window.setTimeout(() => {
        message.classList.add("message-leaving");
        window.setTimeout(() => message.remove(), 250);
      }, 6000);
    });
  });
})();
