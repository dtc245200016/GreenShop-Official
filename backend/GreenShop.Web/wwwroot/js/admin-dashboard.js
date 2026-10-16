(() => {
    "use strict";
    const reduced=matchMedia("(prefers-reduced-motion: reduce)");
    const motions=new Map();
    const animate=(element,frames,options)=>{
        motions.get(element)?.cancel();if(reduced.matches||!element.animate)return;
        const motion=element.animate(frames,options);motions.set(element,motion);
        motion.addEventListener("finish",()=>{if(motions.get(element)===motion)motions.delete(element);});
    };
    const reveal=(element,items,axis)=>{
        const enter=()=>{
            element.dataset.chartRevealed="true";
            items.forEach((item,i)=>animate(item,[{transform:`scale${axis}(.02)`,opacity:.35},{transform:`scale${axis}(1)`,opacity:1}],
                {duration:720,delay:i*Math.min(35,260/Math.max(1,items.length)),easing:"cubic-bezier(.16,1,.3,1)",fill:"backwards"}));
        };
        if(reduced.matches||!("IntersectionObserver" in window)){enter();return;}
        const observer=new IntersectionObserver(entries=>{
            if(entries.some(e=>e.isIntersecting)){observer.disconnect();enter();}
        },{threshold:.15});observer.observe(element);
    };
    document.querySelectorAll("[data-chart]").forEach(chart => {
        // SVG text otherwise shrinks with its 900-unit viewBox on narrow screens.
        const svg=chart.querySelector(".dash-svg");
        const labels=[...chart.querySelectorAll(".dash-axis")];
        const sizeLabels=()=>{
            const scale=svg?.getScreenCTM()?.a;
            if(!scale||scale<=0)return;
            const width=svg.getBoundingClientRect().width;
            const capacity=Math.max(2,Math.floor(width/100));
            const step=Math.max(1,Math.ceil((labels.length-1)/(capacity-1)));
            labels.forEach((label,i)=>{
                label.style.fontSize=`${14/scale}px`;
                label.style.display=i===labels.length-1||i%step===0?"":"none";
                if(i===0)label.setAttribute("text-anchor","start");
                if(i===labels.length-1)label.setAttribute("text-anchor","end");
            });
        };
        sizeLabels();
        const labelObserver="ResizeObserver" in window?new ResizeObserver(sizeLabels):null;
        if(svg)labelObserver?.observe(svg);
        if(!labelObserver)window.addEventListener("resize",sizeLabels);
        window.addEventListener("pagehide",()=>labelObserver?.disconnect(),{once:true});
        window.addEventListener("pageshow",()=>{if(svg)labelObserver?.observe(svg);sizeLabels();});
        const tooltip = chart.querySelector("[role=tooltip]");
        const selection=chart.closest(".dash-panel").querySelector("[data-chart-selection]");
        const bars=[...chart.querySelectorAll(".dash-bar")];let selected;
        const hide = () => { tooltip.hidden = true; };
        bars.forEach(bar => {
            const show = () => {
                tooltip.textContent = `${bar.dataset.label} · ${bar.dataset.value}`;
                tooltip.hidden = false;
                const area = chart.getBoundingClientRect(), point = bar.getBoundingClientRect();
                tooltip.style.left = `${Math.max(0, Math.min(point.left - area.left, area.width - tooltip.offsetWidth))}px`;
                tooltip.style.top = `${Math.max(0, point.top - area.top - tooltip.offsetHeight - 8)}px`;
            };
            bar.addEventListener("mouseenter",show);bar.addEventListener("focus",show);
            bar.addEventListener("mouseleave",hide);bar.addEventListener("blur",hide);
            const choose=()=>{
                selected?.classList.remove("is-selected");selected?.setAttribute("aria-pressed","false");selected=bar;
                bar.classList.add("is-selected");bar.setAttribute("aria-pressed","true");
                selection.textContent=`${bar.dataset.label} · ${bar.dataset.value}`;
                animate(bar,[{transform:"scaleY(.90)"},{transform:"scaleY(1.04)",offset:.58},{transform:"scaleY(1)"}],
                    {duration:420,easing:"cubic-bezier(.2,.7,.3,1)"});show();
            };
            bar.addEventListener("click",choose);
            bar.addEventListener("keydown",event => {
                if(event.key==="Enter"||event.key===" "){event.preventDefault();choose();}
                if(event.key==="Escape"){
                    hide();selected?.classList.remove("is-selected");selected?.setAttribute("aria-pressed","false");selected=null;
                    selection.textContent="Chọn một cột để xem giá trị của ngày hoặc tháng đó.";
                }
            });
        });
        reveal(chart,bars,"Y");
    });
    document.querySelectorAll(".dash-statuses").forEach(panel=>reveal(panel,[...panel.querySelectorAll(".dash-status-track>span")],"X"));
    reduced.addEventListener("change",()=>{if(reduced.matches){motions.forEach(m=>m.cancel());motions.clear();}});
    window.addEventListener("pagehide",()=>{motions.forEach(m=>m.cancel());motions.clear();});
    const fallback = img => { if (img.dataset.fallback) return; img.dataset.fallback = "true"; img.src = "/images/product-placeholder.svg"; };
    document.querySelectorAll("img[data-dashboard-image]").forEach(img => { img.addEventListener("error",()=>fallback(img)); if (img.complete && !img.naturalWidth) fallback(img); });
    const form = document.querySelector(".dash-filter");
    form?.addEventListener("submit",event => {
        if (form.dataset.busy) { event.preventDefault(); return; }
        form.dataset.busy = "true";form.setAttribute("aria-busy","true");
        const button = form.querySelector("button[type=submit]");button.style.minWidth = `${button.offsetWidth}px`;
        button.disabled = true;button.textContent = "Đang tải…";
    });
    window.addEventListener("pageshow",event => { if (event.persisted && form?.dataset.busy) window.location.reload(); });
})();
