(() => {
    "use strict";
    const dialog = document.getElementById("categoryConfirmModal");
    dialog?.addEventListener("keydown", event => {
        if (event.key !== "Tab") return;
        const controls = [...dialog.querySelectorAll('a[href], button:not(:disabled), input:not(:disabled):not([type="hidden"]), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')]
            .filter(element => element.getClientRects().length > 0);
        if (controls.length === 0) return;
        const first = controls[0];
        const last = controls[controls.length - 1];
        if ((event.shiftKey && (document.activeElement === first || document.activeElement === dialog))
            || (!event.shiftKey && document.activeElement === last)) {
            event.preventDefault();
            (event.shiftKey ? last : first).focus();
        }
    });
    dialog?.addEventListener("show.bs.modal", event => {
        const trigger = event.relatedTarget;
        if (!trigger?.dataset.confirmAction) return;
        const isStatus = trigger.hasAttribute("data-confirm-status");
        const form = document.getElementById("categoryConfirmForm");
        form.action = trigger.dataset.confirmAction;
        document.getElementById("categoryConfirmTitle").textContent = trigger.dataset.confirmLabel;
        document.getElementById("categoryConfirmName").textContent = trigger.dataset.confirmName;
        document.getElementById("categoryConfirmDescription").textContent = isStatus
            ? "Thay đổi trạng thái không xóa sản phẩm đã liên kết. Danh mục ngừng hoạt động sẽ không có trong lựa chọn mới."
            : "Bạn có chắc muốn xóa danh mục này? Thao tác không thể hoàn tác.";
        const status = document.getElementById("categoryConfirmStatus");
        status.disabled = !isStatus;
        status.value = isStatus ? trigger.dataset.confirmStatus : "";
        const submit = document.getElementById("categoryConfirmSubmit");
        submit.className = "btn " + (isStatus ? "category-primary" : "category-danger");
        submit.querySelector("[data-submit-label]").textContent = trigger.dataset.confirmLabel;
    });

    document.querySelectorAll("[data-character-count]").forEach(input => {
        const counter = document.getElementById(input.dataset.characterCount);
        const update = () => { if (counter) counter.textContent = `${input.value.length}/${input.maxLength}`; };
        input.addEventListener("input", update);
        update();
    });

    document.querySelectorAll("form[data-submit-once]").forEach(form => {
        form.addEventListener("submit", event => {
            if (form.dataset.submitting === "true") {
                event.preventDefault();
                return;
            }
            if (!form.checkValidity()) return;
            form.dataset.submitting = "true";
            form.setAttribute("aria-busy", "true");
            form.querySelectorAll('button[type="submit"]:not(:disabled)').forEach(button => {
                button.dataset.busyDisabled = "true";
                button.disabled = true;
                const label = button.querySelector("[data-submit-label]");
                if (label) {
                    label.dataset.originalLabel = label.textContent;
                    label.textContent = "Đang xử lý…";
                }
            });
        });
    });

    window.addEventListener("pageshow", () => {
        document.querySelectorAll('form[data-submit-once][data-submitting="true"]').forEach(form => {
            delete form.dataset.submitting;
            form.removeAttribute("aria-busy");
            form.querySelectorAll('[data-busy-disabled="true"]').forEach(button => {
                button.disabled = false;
                delete button.dataset.busyDisabled;
                const label = button.querySelector("[data-original-label]");
                if (label) label.textContent = label.dataset.originalLabel;
            });
        });
    });
})();
