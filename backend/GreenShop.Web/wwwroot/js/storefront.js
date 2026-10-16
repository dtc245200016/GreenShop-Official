(() => {
    "use strict";
    const placeholder = "/images/product-placeholder.svg";
    const menus = document.querySelectorAll("details[data-shop-menu]");
    const dialogs = document.querySelectorAll("dialog.shop-dialog");
    let dialogTrigger = null;
    const syncDialogs = () => {
        const anyOpen = [...dialogs].some(dialog => dialog.open);
        document.documentElement.classList.toggle("shop-dialog-open", anyOpen);
        document.querySelectorAll("[data-open-dialog]").forEach(button => {
            button.setAttribute("aria-expanded", String(document.getElementById(button.dataset.openDialog)?.open === true));
        });
    };
    dialogs.forEach(dialog => dialog.addEventListener("close", () => {
        syncDialogs();
        if (dialogTrigger && dialogTrigger.getClientRects().length) dialogTrigger.focus();
    }));
    document.addEventListener("click", event => {
        const trigger = event.target.closest("[data-open-dialog]");
        if (trigger) {
            menus.forEach(menu => { menu.open = false; });
            const dialog = document.getElementById(trigger.dataset.openDialog);
            if (dialog && !dialog.open) { dialogTrigger = trigger; dialog.showModal(); syncDialogs(); }
        }
        const close = event.target.closest("[data-close-dialog]");
        if (close) close.closest("dialog").close();
        if (event.target instanceof HTMLDialogElement && event.target.open) {
            const bounds = event.target.getBoundingClientRect();
            if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.target.close();
        }
        menus.forEach(menu => { if (!menu.contains(event.target)) menu.open = false; });
    });
    menus.forEach(menu => menu.addEventListener("toggle", () => {
        if (menu.open) menus.forEach(other => { if (other !== menu) other.open = false; });
    }));
    document.addEventListener("keydown", event => {
        if (event.key === "Tab") {
            const dialog = [...dialogs].find(item => item.open);
            if (dialog) {
                const focusable = [...dialog.querySelectorAll('a[href], button, input, select, textarea, summary, [tabindex]')]
                    .filter(item => !item.disabled && item.tabIndex >= 0 && item.getClientRects().length);
                const first = focusable[0], last = focusable[focusable.length - 1];
                if (first && (event.shiftKey ? document.activeElement === first : document.activeElement === last)) {
                    event.preventDefault();
                    (event.shiftKey ? last : first).focus();
                }
            }
        }
        if (event.key !== "Escape") return;
        menus.forEach(menu => {
            if (menu.open) { menu.open = false; menu.querySelector("summary").focus(); }
        });
    });
    const desktop = matchMedia("(min-width: 1100px)");
    desktop.addEventListener("change", () => { if (desktop.matches) document.getElementById("shop-navigation-dialog")?.close(); });
    const header = document.querySelector("[data-shop-header]");
    let scrolled = false;
    const updateHeader = () => {
        const next = scrollY > 8;
        if (next !== scrolled) { scrolled = next; header?.classList.toggle("is-scrolled", scrolled); }
    };
    addEventListener("scroll", updateHeader, { passive: true });
    updateHeader();
    document.addEventListener("change", event => { if (event.target.matches("[data-sort-submit]")) event.target.form.requestSubmit(); });
    const fallback = img => { if (img.matches("img[data-product-image]") && !img.dataset.fallback) { img.dataset.fallback = "true"; img.src = placeholder; } };
    document.addEventListener("error", event => { if (event.target instanceof HTMLImageElement) fallback(event.target); }, true);
    document.querySelectorAll("img[data-product-image]").forEach(img => { if (img.complete && img.naturalWidth === 0) fallback(img); });
    document.addEventListener("click", event => {
        const button = event.target.closest("[data-quantity-step]");
        if (!button) return;
        const input = button.closest(".quantity-control").querySelector("input");
        const min = Number(input.min) || 1, max = Number(input.max) || 1_000_000;
        input.value = String(Math.max(min, Math.min(max, (Number(input.value) || min) + Number(button.dataset.quantityStep))));
        input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    document.addEventListener("submit", event => {
        const form = event.target;
        if (!form.matches("form[data-submit-once]")) return;
        if (form.dataset.submitting === "true") { event.preventDefault(); return; }
        if (!form.checkValidity()) return;
        // Keep the chosen Buy Now endpoint when disabling its submitter.
        if (event.submitter?.hasAttribute("formaction")) form.action = event.submitter.formAction;
        form.dataset.submitting = "true";
        form.setAttribute("aria-busy", "true");
        form.querySelectorAll('button[type="submit"]:not(:disabled)').forEach(button => {
            button.dataset.originalHtml = button.innerHTML;
            button.dataset.busyDisabled = "true";
            button.disabled = true;
            if (button === event.submitter) button.textContent = "Đang xử lý…";
        });
    });
    window.addEventListener("pageshow", () => {
        dialogs.forEach(dialog => { if (dialog.open) dialog.close(); });
        menus.forEach(menu => { menu.open = false; });
        syncDialogs();
        document.querySelectorAll('form[data-submitting="true"]').forEach(form => {
            delete form.dataset.submitting; form.removeAttribute("aria-busy");
            form.querySelectorAll('[data-busy-disabled="true"]').forEach(button => {
                button.innerHTML = button.dataset.originalHtml; button.disabled = false;
                delete button.dataset.originalHtml; delete button.dataset.busyDisabled;
            });
        });
    });
})();
