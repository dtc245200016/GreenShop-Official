(() => {
    "use strict";
    const dialog = document.getElementById("orderConfirmDialog");
    const reason = document.getElementById("orderReason");
    let pendingForm = null, approvedForm = null, trigger = null;
    let closing = false;
    const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
    const toast = document.createElement("div");
    toast.className = "admin-action-feedback";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.hidden = true;
    document.body.append(toast);
    let toastTimer;
    const feedback = (message, error = false) => {
        clearTimeout(toastTimer);
        toast.textContent = message;
        toast.classList.toggle("error", error);
        toast.hidden = false;
        toastTimer = setTimeout(() => { toast.hidden = true; }, 7000);
    };
    const dismiss = () => {
        if (closing || !dialog?.open) return;
        closing = true;
        dialog.classList.add("is-closing");
        setTimeout(() => { dialog.close(); }, reducedMotion.matches ? 0 : 180);
    };
    const resetForms = () => document.querySelectorAll("form[data-order-submit]").forEach(form => {
        delete form.dataset.busy;
        form.removeAttribute("aria-busy");
        form.querySelectorAll("[data-order-busy]").forEach(button => {
            button.innerHTML = button.dataset.originalHtml;
            button.disabled = false;
            button.style.minWidth = "";
            delete button.dataset.orderBusy;
        });
    });
    document.addEventListener("submit", async event => {
        const form = event.target;
        if (!form.matches("form[data-order-submit]")) return;
        if (form.dataset.busy) { event.preventDefault(); return; }
        if (form.hasAttribute("data-order-confirm") && approvedForm !== form) {
            event.preventDefault();
            if (dialog.open || closing) return;
            pendingForm = form;
            trigger = event.submitter;
            document.getElementById("orderConfirmTitle").textContent = form.dataset.confirmTitle;
            document.getElementById("orderConfirmDescription").textContent = form.dataset.confirmDescription;
            let label = form.dataset.confirmLabel || form.dataset.confirmTitle || "Lưu thay đổi";
            if (form.hasAttribute("data-confirm-role")) {
                const select = form.querySelector('[name="TargetRole"]');
                const role = select.options[select.selectedIndex].textContent;
                label = select.value === "1" ? "Cấp quyền quản trị viên" : "Chuyển thành khách hàng";
                document.getElementById("orderConfirmDescription").textContent =
                    `Đổi quyền của ${form.dataset.confirmAccount} từ ${form.dataset.confirmCurrentRole} sang ${role}? ` +
                    (select.value === "1" ? "Người này sẽ có quyền quản lý sản phẩm, đơn hàng và tài khoản. " : "Người này sẽ mất quyền truy cập khu vực quản trị. ") +
                    "Các phiên đăng nhập hiện có sẽ bị thu hồi; người dùng cần đăng nhập lại.";
            }
            document.getElementById("orderConfirmSubmit").textContent = label;
            const needsReason = !!form.dataset.confirmReason;
            document.getElementById("orderReasonField").hidden = !needsReason;
            document.querySelector('label[for="orderReason"]').textContent = form.dataset.confirmReason || "Ghi chú";
            reason.required = needsReason;
            reason.value = "";
            reason.setCustomValidity("");
            dialog.classList.toggle("is-danger", form.hasAttribute("data-confirm-danger") && form.dataset.confirmDanger !== "false" || form.querySelector('[name="TargetRole"]')?.value === "0");
            dialog.showModal();
            document.documentElement.classList.add("order-modal-open");
            return;
        }
        if (!form.checkValidity()) return;
        event.preventDefault();
        const payload = new URLSearchParams(new FormData(form));
        form.dataset.busy = "true";
        form.setAttribute("aria-busy", "true");
        form.querySelectorAll('button[type="submit"]:not(:disabled)').forEach(button => {
            button.dataset.originalHtml = button.innerHTML;
            button.dataset.orderBusy = "true";
            button.style.minWidth = `${button.getBoundingClientRect().width}px`;
            button.disabled = true;
            button.textContent = "Đang lưu…";
        });
        // Keep the current scroll position and page chrome; server remains the source of truth.
        const scrollTop = window.scrollY;
        try {
            const response = await fetch(form.action, { method: "POST", body: payload, credentials: "same-origin", signal: AbortSignal.timeout(25000) });
            const address = new URL(response.url);
            if (address.origin !== location.origin) throw new Error("unexpected redirect");
            const html = new DOMParser().parseFromString(await response.text(), "text/html");
            const next = html.querySelector(".order-admin");
            const current = document.querySelector(".order-admin");
            if (!next || !current) {
                if (["/Account/Login", "/Account/AccessDenied", "/Admin/Account/Login", "/Admin/Account/AccessDenied"].includes(address.pathname)) location.assign(address.href);
                else { feedback("Chưa thể lưu thay đổi. Hãy tải lại trang để kiểm tra trước khi thử lại.", true); resetForms(); }
                return;
            }
            const notice = next.querySelector("[data-action-feedback]")?.textContent.trim();
            next.querySelectorAll("[data-action-feedback]").forEach(element => element.remove());
            current.replaceWith(next);
            document.title = html.title;
            if (response.redirected) history.replaceState(null, "", address.href);
            // Profile edits can change the signed-in name without reloading the navigation.
            const greeting = html.querySelector('.admin-topbar strong');
            const existingGreeting = document.querySelector('.admin-topbar strong');
            if (greeting && existingGreeting) existingGreeting.textContent = greeting.textContent;
            window.scrollTo({ top: scrollTop, behavior: "instant" });
            feedback(notice || (response.ok ? "Đã lưu thay đổi." : "Chưa thể lưu thay đổi."), !response.ok);
            const replacement = next.querySelector(`form[action="${new URL(form.action).pathname}"] button[type="submit"]`);
            replacement?.focus({ preventScroll: true });
            initImages();
            initRoleControls();
        } catch {
            feedback("Chưa xác định được kết quả lưu. Hãy tải lại trang để kiểm tra trước khi thử lại.", true);
            resetForms();
        }
    });
    if (dialog) {
        document.getElementById("orderConfirmForm").addEventListener("submit", event => {
            event.preventDefault();
            if (!pendingForm) return;
            if (reason.required && !reason.value.trim()) { reason.setCustomValidity("Vui lòng nhập căn cứ hoặc lý do."); reason.reportValidity(); return; }
            const form = pendingForm;
            const note = form.querySelector("[data-confirm-note]");
            if (note) note.value = reason.value.trim();
            approvedForm = form;
            dialog.close();
            form.requestSubmit();
            approvedForm = null;
        });
        reason.addEventListener("input", () => reason.setCustomValidity(""));
        dialog.addEventListener("close", () => {
            closing = false;
            dialog.classList.remove("is-closing");
            document.documentElement.classList.remove("order-modal-open");
            pendingForm = null;
            if (trigger && !trigger.disabled && trigger.isConnected) trigger.focus({ preventScroll: true });
        });
        dialog.addEventListener("cancel", event => { event.preventDefault(); dismiss(); });
        dialog.addEventListener("click", event => {
            if (event.target.closest("[data-order-close]")) dismiss();
            if (event.target === dialog) {
                const bounds = dialog.getBoundingClientRect();
                if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dismiss();
            }
        });
        dialog.addEventListener("keydown", event => {
            if (event.key !== "Tab") return;
            const controls = [...dialog.querySelectorAll("button, textarea")].filter(e => !e.disabled && e.getClientRects().length);
            const first = controls[0], last = controls[controls.length - 1];
            if (event.shiftKey ? document.activeElement === first : document.activeElement === last) {
                event.preventDefault(); (event.shiftKey ? last : first).focus();
            }
        });
    }
    const fallback = img => { if (!img.dataset.orderFallback) { img.dataset.orderFallback = "true"; img.src = "/images/product-placeholder.svg"; } };
    document.addEventListener("error", event => { if (event.target.matches?.("img[data-order-image]")) fallback(event.target); }, true);
    const initImages = () => document.querySelectorAll("img[data-order-image]").forEach(img => { if (img.complete && !img.naturalWidth) fallback(img); });
    const updateRoleControl = select => { select.closest("form").querySelector('button[type="submit"]').disabled = select.value === select.dataset.currentRole; };
    const initRoleControls = () => document.querySelectorAll('[name="TargetRole"][data-current-role]').forEach(updateRoleControl);
    document.addEventListener("change", event => { if (event.target.matches('[name="TargetRole"][data-current-role]')) updateRoleControl(event.target); });
    initImages();
    initRoleControls();
    document.querySelector("[data-order-print]")?.addEventListener("click", () => print());
    window.addEventListener("pageshow", () => { if (dialog?.open) dialog.close(); resetForms(); });
})();
