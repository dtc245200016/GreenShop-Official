// Visual feedback only. Existing storefront.js owns menus and form submissions.
(() => {
    "use strict";
    if (!document.body.classList.contains("storefront")) return;
    const key="greenshop.theme",root=document.documentElement;
    const system=matchMedia("(prefers-color-scheme: dark)"),reduced=matchMedia("(prefers-reduced-motion: reduce)");
    let preference=null,transition;
    try { const saved=localStorage.getItem(key);if(saved==="light"||saved==="dark")preference=saved; } catch {}
    const apply=(theme,animate=false)=>{
        if(animate&&!reduced.matches){root.dataset.themeChanging="true";clearTimeout(transition);transition=setTimeout(()=>delete root.dataset.themeChanging,320);}
        root.dataset.theme=theme;
        document.querySelector('meta[name="theme-color"]')?.setAttribute("content",theme==="dark"?"#142d21":"#fbfdf9");
        document.querySelectorAll("[data-theme-toggle]").forEach(button=>{
            const label=theme==="dark"?"Chuyển sang giao diện sáng":"Chuyển sang giao diện tối";
            button.setAttribute("aria-label",label);button.setAttribute("aria-pressed",String(theme==="dark"));button.title=label;
            button.querySelector("[data-theme-label]").textContent=label;
        });
    };
    apply(preference||(system.matches?"dark":"light"));
    document.addEventListener("click",event=>{
        if(!event.target.closest("[data-theme-toggle]"))return;
        const theme=root.dataset.theme==="dark"?"light":"dark";
        preference=theme;try{localStorage.setItem(key,theme);}catch{}
        apply(theme,true);
    });
    addEventListener("storage",event=>{
        if(event.key!==key&&event.key!==null)return;
        preference=event.newValue==="dark"||event.newValue==="light"?event.newValue:null;
        apply(preference||(system.matches?"dark":"light"),true);
    });
    system.addEventListener("change",()=>{if(!preference)apply(system.matches?"dark":"light",true);});
    reduced.addEventListener("change",()=>{if(reduced.matches){clearTimeout(transition);delete root.dataset.themeChanging;}});
    addEventListener("pagehide",()=>clearTimeout(transition));
    // One delegated listener per vine. Animate only nearby leaves, never layout or an idle loop.
    document.querySelectorAll("[data-botanical-nav]").forEach(vine=>{
        const leaves=[...vine.querySelectorAll("[data-vine-position]")];
        let bounds,previous=-1,last=0;
        const sway=event=>{
            if(reduced.matches||event.pointerType==="touch")return;
            bounds??=vine.getBoundingClientRect();
            const x=(event.clientX-bounds.left)/bounds.width*1200,index=Math.round(x/90);
            if(index===previous||performance.now()-last<100)return;
            previous=index;last=performance.now();
            leaves.filter(leaf=>Math.abs(Number(leaf.dataset.vinePosition)-x)<140).forEach((leaf,i)=>{
                leaf.getAnimations().forEach(animation=>animation.cancel());
                const direction=i%2?1:-1;
                leaf.animate([{transform:"rotate(0deg) translateY(0)"},{transform:`rotate(${direction*7}deg) translateY(-2px)`,offset:.32},{transform:`rotate(${-direction*3}deg) translateY(1px)`,offset:.72},{transform:"rotate(0deg) translateY(0)"}],
                    {duration:650,delay:Math.min(160,Math.abs(Number(leaf.dataset.vinePosition)-x)*.7+i*15),easing:"cubic-bezier(.25,.7,.35,1)"});
            });
        };
        vine.addEventListener("pointerenter",event=>{bounds=vine.getBoundingClientRect();previous=-1;sway(event);});
        vine.addEventListener("pointermove",sway,{passive:true});
        vine.addEventListener("pointerleave",()=>{bounds=undefined;previous=-1;});
        addEventListener("resize",()=>{bounds=undefined;},{passive:true});
        reduced.addEventListener("change",()=>{if(reduced.matches)leaves.forEach(leaf=>leaf.getAnimations().forEach(animation=>animation.cancel()));});
    });
})();
(() => {
    "use strict";
    const reduced=matchMedia("(prefers-reduced-motion: reduce)");
    const timers=new WeakMap();
    document.addEventListener("pointerdown",event=>{
        if(reduced.matches || !event.isPrimary || event.button!==0)return;
        const button=event.target.closest(".storefront :is(.shop-btn,.shop-icon-button,.auth-form-wrapper .btn)");
        if(!button || button.disabled || button.classList.contains("disabled"))return;
        const bounds=button.getBoundingClientRect();
        button.style.setProperty("--press-x",`${event.clientX-bounds.left}px`);
        button.style.setProperty("--press-y",`${event.clientY-bounds.top}px`);
        clearTimeout(timers.get(button));button.classList.add("customer-pressed");
        timers.set(button,setTimeout(()=>button.classList.remove("customer-pressed"),260));
    });
    document.querySelectorAll("[data-product-carousel]").forEach(root=>{
        const track=root.querySelector("[data-carousel-track]");if(!track)return;
        const cards=[...track.querySelectorAll(".shop-product-card")];
        const previous=root.querySelector("[data-carousel-prev]"),next=root.querySelector("[data-carousel-next]");
        const toggle=root.querySelector("[data-carousel-toggle]"),dots=root.querySelector("[data-carousel-dots]");
        const counter=root.querySelector("[data-carousel-counter]"),announcement=root.querySelector("[data-carousel-announcement]");
        let positions=[0],current=0,direction=1,visible=false,hover=false,userPaused=reduced.matches,focusPaused=false;
        let autoTimer,scrollTimer,frame,resizeFrame,drag=null,suppressClick=false,suppressTimer,pointerIntent;
        const canRotate=()=>positions.length>1&&!userPaused&&!focusPaused&&!hover&&!drag&&visible&&!document.hidden&&!reduced.matches;
        const nearest=()=>positions.reduce((best,p,i)=>Math.abs(p-track.scrollLeft)<Math.abs(positions[best]-track.scrollLeft)?i:best,0);
        const schedule=()=>{
            clearTimeout(autoTimer);root.dataset.carouselAutoplay=canRotate()?"running":"paused";
            if(canRotate())autoTimer=setTimeout(()=>{
                current=nearest();if(current===positions.length-1)direction=-1;else if(current===0)direction=1;
                go(current+direction,false);
            },5000);
        };
        const render=()=>{
            current=nearest();previous.disabled=current===0;next.disabled=current===positions.length-1;
            counter.textContent=`${current+1} / ${positions.length}`;
            dots.querySelectorAll("button").forEach((dot,i)=>dot.setAttribute("aria-current",String(i===current)));
            const paused=userPaused||focusPaused||reduced.matches;
            toggle.setAttribute("aria-pressed",String(paused));toggle.disabled=reduced.matches;
            toggle.querySelector("span").textContent=reduced.matches?"Trượt thủ công":paused?"Tiếp tục tự trượt":"Tạm dừng tự trượt";
            toggle.querySelector("i").className=`fa-solid fa-${paused?"play":"pause"}`;
        };
        const go=(index,manual=true)=>{
            clearTimeout(autoTimer);index=Math.max(0,Math.min(positions.length-1,index));
            if(manual)announcement.textContent=`Nhóm sản phẩm ${index+1} trên ${positions.length}.`;
            track.scrollTo({left:positions[index],behavior:reduced.matches?"instant":"smooth"});
            schedule();
        };
        const resize=()=>{
            const maximum=Math.max(0,track.scrollWidth-track.clientWidth),origin=cards[0]?.offsetLeft||0;
            const values=cards.map(c=>Math.min(maximum,Math.max(0,c.offsetLeft-origin)));
            positions=values.filter((p,i)=>i===0||Math.abs(p-values[i-1])>1);
            if(!positions.length)positions=[0];
            dots.replaceChildren();positions.forEach((_,i)=>{
                const dot=document.createElement("button");dot.type="button";dot.className="home-carousel-dot";
                dot.setAttribute("aria-label",`Xem nhóm sản phẩm ${i+1}`);dot.setAttribute("aria-controls",track.id);
                dot.addEventListener("click",()=>go(i));dots.append(dot);
            });
            root.querySelectorAll("[data-carousel-controls]").forEach(el=>el.hidden=positions.length<2);
            render();schedule();
        };
        previous.addEventListener("click",()=>go(nearest()-1));next.addEventListener("click",()=>go(nearest()+1));
        toggle.addEventListener("pointerdown",()=>{pointerIntent=userPaused||focusPaused;});
        toggle.addEventListener("click",()=>{
            const resume=pointerIntent??(userPaused||focusPaused);pointerIntent=undefined;
            userPaused=!resume;if(resume)focusPaused=false;render();schedule();
        });
        root.addEventListener("pointerenter",event=>{if(event.pointerType!=="touch"){hover=true;schedule();}});
        root.addEventListener("pointerleave",()=>{hover=false;schedule();});
        root.addEventListener("focusin",()=>{focusPaused=true;render();schedule();});
        track.addEventListener("keydown",event=>{
            if(event.target!==track)return;
            const index=event.key==="ArrowRight"?nearest()+1:event.key==="ArrowLeft"?nearest()-1:event.key==="Home"?0:event.key==="End"?positions.length-1:null;
            if(index!==null){event.preventDefault();go(index);}
        });
        track.addEventListener("scroll",()=>{
            clearTimeout(autoTimer);cancelAnimationFrame(frame);frame=requestAnimationFrame(render);
            clearTimeout(scrollTimer);scrollTimer=setTimeout(schedule,160);
        },{passive:true});
        track.querySelectorAll("img").forEach(img=>img.draggable=false);
        track.addEventListener("dragstart",event=>event.preventDefault());
        track.addEventListener("pointerdown",event=>{
            suppressClick=false;clearTimeout(suppressTimer);
            if(event.pointerType!=="mouse"||event.button!==0||!event.isPrimary||event.target.closest("button,input,select,textarea"))return;
            drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:track.scrollLeft,started:false};schedule();
        });
        track.addEventListener("pointermove",event=>{
            if(!drag||event.pointerId!==drag.id)return;
            const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
            if(!drag.started){
                if(Math.abs(dy)>Math.abs(dx)&&Math.abs(dy)>8){drag=null;schedule();return;}
                if(Math.abs(dx)<8)return;
                drag.started=true;track.classList.add("is-dragging");track.setPointerCapture(event.pointerId);
            }
            event.preventDefault();track.scrollLeft=drag.left-dx;
        });
        const finishDrag=event=>{
            if(!drag||event.pointerId!==drag.id)return;
            const moved=drag.started;drag=null;
            if(track.hasPointerCapture(event.pointerId))track.releasePointerCapture(event.pointerId);
            track.classList.remove("is-dragging");
            if(moved){suppressClick=true;clearTimeout(suppressTimer);suppressTimer=setTimeout(()=>suppressClick=false,350);go(nearest());}
            schedule();
        };
        track.addEventListener("pointerup",finishDrag);track.addEventListener("pointercancel",finishDrag);
        window.addEventListener("pointerup",finishDrag);window.addEventListener("pointercancel",finishDrag);
        track.addEventListener("lostpointercapture",()=>{if(drag){drag=null;track.classList.remove("is-dragging");schedule();}});
        track.addEventListener("click",event=>{if(suppressClick){event.preventDefault();event.stopImmediatePropagation();suppressClick=false;}},true);
        if("IntersectionObserver" in window){
            const observer=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;schedule();},{threshold:.12});observer.observe(root);
        }else visible=true;
        if("ResizeObserver" in window)new ResizeObserver(()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(resize);}).observe(track);
        else window.addEventListener("resize",resize);
        reduced.addEventListener("change",()=>{if(reduced.matches){userPaused=true;track.scrollTo({left:positions[nearest()],behavior:"instant"});}render();schedule();});
        document.addEventListener("visibilitychange",schedule);
        window.addEventListener("pagehide",()=>{clearTimeout(autoTimer);clearTimeout(scrollTimer);clearTimeout(suppressTimer);cancelAnimationFrame(frame);cancelAnimationFrame(resizeFrame);});
        window.addEventListener("pageshow",()=>{resize();schedule();});
        resize();
    });
})();
