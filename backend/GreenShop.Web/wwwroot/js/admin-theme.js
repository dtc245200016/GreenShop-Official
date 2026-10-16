// Decorative feedback only: never intercept navigation, validation, or submission.
(() => {
    "use strict";
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const timers = new WeakMap();
    document.addEventListener("pointerdown", event => {
        if (reduced.matches || !event.isPrimary || event.button !== 0) return;
        const button = event.target.closest(".admin-shell :is(.btn,.order-btn,.dash-btn)");
        if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") return;
        const box = button.getBoundingClientRect();
        button.style.setProperty("--press-x", `${event.clientX-box.left}px`);
        button.style.setProperty("--press-y", `${event.clientY-box.top}px`);
        clearTimeout(timers.get(button));
        button.classList.add("admin-pressed");
        timers.set(button,setTimeout(()=>button.classList.remove("admin-pressed"),260));
    });
})();
