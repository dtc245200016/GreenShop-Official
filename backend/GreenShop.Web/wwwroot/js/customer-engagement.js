(() => {
    "use strict";
    document.querySelectorAll('img[data-review-product-image]').forEach(image=>{
        const fallback=()=>{if(image.getAttribute('src')!=='/images/product-placeholder.svg')image.src='/images/product-placeholder.svg';};
        image.addEventListener('error',fallback);if(image.complete&&!image.naturalWidth)fallback();
    });
    const reduced=matchMedia("(prefers-reduced-motion: reduce)");
    document.querySelectorAll('input[type="file"]').forEach((input,index)=>{
        if(!/image\/(jpeg|png|webp)|\.(jpg|jpeg|png|webp)/i.test(input.accept))return;
        const picker=document.createElement("div"),button=document.createElement("button"),icon=document.createElement("i"),name=document.createElement("span");
        picker.className="image-file-picker";button.type="button";button.className="file-picker-button";button.disabled=input.disabled;
        icon.className="fa-regular fa-image";icon.setAttribute("aria-hidden","true");button.append(icon,document.createTextNode("Chọn file"));
        name.className="file-picker-name";name.id=`image-file-name-${index}`;name.setAttribute("role","status");name.setAttribute("aria-live","polite");button.setAttribute("aria-describedby",name.id);
        input.before(picker);picker.append(input,button,name);input.classList.add("image-file-input");
        let timer=0;
        const update=()=>{const files=[...input.files];name.textContent=files.length>1?`${files.length} file: ${files.map(f=>f.name).join(", ")}`:files[0]?.name||"Chưa chọn file";name.title=files.map(f=>f.name).join(", ");clearTimeout(timer);picker.classList.remove("is-selected");if(files.length&&!reduced.matches){void picker.offsetWidth;picker.classList.add("is-selected");timer=setTimeout(()=>picker.classList.remove("is-selected"),260);}};
        button.addEventListener("click",()=>input.click());input.addEventListener("change",update);input.addEventListener("invalid",()=>button.focus());input.form?.addEventListener("reset",()=>setTimeout(update,0));update();
    });
    document.querySelectorAll("form[data-engagement-submit]").forEach(form=>{
        form.addEventListener("submit",e=>{
            if(form.dataset.engagementBusy==="true"){e.preventDefault();return;}if(e.defaultPrevented||!form.checkValidity())return;
            form.dataset.engagementBusy="true";form.setAttribute("aria-busy","true");form.querySelectorAll('button[type="submit"]').forEach(button=>button.disabled=true);
        });
        window.addEventListener("pageshow",()=>{delete form.dataset.engagementBusy;form.removeAttribute("aria-busy");form.querySelectorAll('button[type="submit"]').forEach(button=>button.disabled=false);});
    });
    document.querySelectorAll("[data-hero-slider]").forEach(root=>{
        const track=root.querySelector("[data-hero-track]"),slides=[...root.querySelectorAll("[data-hero-slide]")];
        if(!track||slides.length<2)return;
        let index=0,timer=0,paused=false,visible=true,start=null,dragging=false,suppressClick=false,wrapping=false,wrapTimer=0;
        const clone=slide=>{const copy=slide.cloneNode(true);copy.removeAttribute("data-hero-slide");copy.removeAttribute("data-product-id");copy.inert=true;copy.setAttribute("aria-hidden","true");copy.setAttribute("data-hero-clone","");copy.querySelectorAll("[id]").forEach(e=>e.removeAttribute("id"));return copy;};
        track.prepend(clone(slides.at(-1)));track.append(clone(slides[0]));
        const normalize=()=>{clearTimeout(wrapTimer);wrapping=false;track.style.transition="none";track.style.transform=`translateX(-${(index+1)*100}%)`;void track.offsetWidth;track.style.transition="";};
        normalize();
        const pause=root.querySelector("[data-hero-pause]"),counter=root.querySelector("[data-hero-counter]"),announcement=root.querySelector("[data-hero-announcement]");
        const schedule=()=>{clearTimeout(timer);const running=!paused&&!document.hidden&&visible&&!reduced.matches&&!start;root.dataset.heroAutoplay=running?"running":"paused";if(running)timer=setTimeout(()=>go(index+1,false),5000);};
        const go=(value,manual=true)=>{
            if(wrapping)normalize();index=(value+slides.length)%slides.length;
            const edge=value<0||value>=slides.length;
            const position=edge&&!reduced.matches?(value<0?0:slides.length+1):index+1;
            track.style.transform=`translateX(-${position*100}%)`;
            if(edge&&!reduced.matches){wrapping=true;wrapTimer=setTimeout(normalize,650);}
            slides.forEach((slide,i)=>{slide.inert=i!==index;slide.setAttribute("aria-hidden",String(i!==index));});
            for(const offset of [-1,0,1])slides[(index+offset+slides.length)%slides.length].querySelector("img").loading="eager";
            counter.textContent=`${index+1} / ${slides.length}`;root.dataset.heroIndex=String(index);
            if(manual)announcement.textContent=`${slides[index].querySelector("img").alt}, sản phẩm ${index+1} trên ${slides.length}`;
            schedule();
        };
        root.querySelector("[data-hero-prev]").addEventListener("click",()=>go(index-1));root.querySelector("[data-hero-next]").addEventListener("click",()=>go(index+1));
        pause.addEventListener("click",()=>{paused=!paused;pause.setAttribute("aria-pressed",String(paused));pause.textContent=paused?"Bật tự trượt":"Tạm dừng tự trượt";schedule();});
        document.addEventListener("visibilitychange",schedule);reduced.addEventListener("change",schedule);
        root.addEventListener("keydown",e=>{if(e.target.matches("input,textarea,select")||!["ArrowLeft","ArrowRight"].includes(e.key))return;e.preventDefault();go(index+(e.key==="ArrowRight"?1:-1));});
        const viewport=root.querySelector(".hero-slider-viewport");
        viewport.addEventListener("pointerdown",e=>{if(e.button!==0||e.target.closest("button,input,textarea,form"))return;if(wrapping)normalize();start={x:e.clientX,y:e.clientY,id:e.pointerId};dragging=false;schedule();});
        viewport.addEventListener("pointermove",e=>{
            if(!start||e.pointerId!==start.id)return;const dx=e.clientX-start.x,dy=e.clientY-start.y;
            if(!dragging&&Math.abs(dy)>Math.abs(dx)+8){start=null;schedule();return;}
            if(!dragging&&Math.abs(dx)>10){dragging=true;viewport.setPointerCapture(e.pointerId);track.classList.add("is-dragging");}
            if(dragging){e.preventDefault();track.style.transform=`translateX(calc(-${(index+1)*100}% + ${dx}px))`;}
        });
        const end=e=>{if(!start)return;const dx=e.clientX-start.x;start=null;track.classList.remove("is-dragging");if(dragging){suppressClick=true;go(index+(Math.abs(dx)>Math.min(65,viewport.clientWidth*.15)?(dx<0?1:-1):0));setTimeout(()=>{suppressClick=false;},0);}else schedule();dragging=false;};
        viewport.addEventListener("pointerup",end);viewport.addEventListener("pointercancel",()=>{start=null;dragging=false;track.classList.remove("is-dragging");go(index,false);});
        viewport.addEventListener("click",e=>{if(suppressClick){e.preventDefault();e.stopPropagation();}},true);
        new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;schedule();},{threshold:.15}).observe(root);go(0,false);
    });

    const fetchJson=async(url,options={})=>{
        const response=await fetch(url,{credentials:"same-origin",redirect:"error",signal:AbortSignal.timeout(7000),...options});
        if(!response.ok){let data={};try{data=await response.json();}catch{data.message=response.status===429?"Bạn thao tác quá nhanh. Vui lòng đợi rồi thử lại.":"Mất kết nối. Vui lòng thử lại.";}const error=new Error(data.message||"Mất kết nối. Vui lòng thử lại.");error.resetConversation=data.resetConversation===true;throw error;}
        return response.status===204?null:response.json();
    };
    document.querySelectorAll('[data-review-reply-form]').forEach(form=>{
        const button=form.querySelector('button[type="submit"]'),feedback=form.querySelector('[data-reply-feedback]'),input=form.elements.Content,container=form.closest('[data-admin-review]');
        let pending=false;
        form.addEventListener('submit',async event=>{
            event.preventDefault();if(pending||!form.checkValidity())return;
            pending=true;button.disabled=true;form.setAttribute('aria-busy','true');feedback.textContent='Đang lưu phản hồi…';feedback.classList.remove('is-error');
            try{
                const data=await fetchJson(form.action,{method:'POST',body:new FormData(form),headers:{'X-Requested-With':'XMLHttpRequest'}});
                container.querySelectorAll('input[name="Version"],input[name="version"]').forEach(field=>field.value=String(data.version));
                let reply=container.querySelector('[data-review-reply]');
                if(!reply){
                    reply=document.createElement('aside');reply.className='review-reply';reply.dataset.reviewReply='';reply.setAttribute('aria-label','Phản hồi từ GreenShop');
                    const header=document.createElement('header'),title=document.createElement('strong'),time=document.createElement('small'),text=document.createElement('p');
                    title.textContent='Phản hồi từ GreenShop';header.append(title,time);reply.append(header,text);container.querySelector('.review-entry').append(reply);
                }
                reply.querySelector('p').textContent=data.content;
                reply.querySelector('small').textContent=new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'short',timeStyle:'short'}).format(new Date(data.updatedAt));
                button.textContent='Cập nhật phản hồi';feedback.textContent=data.message;
            }catch(error){feedback.classList.add('is-error');feedback.textContent=error.message;}
            finally{pending=false;button.disabled=false;form.removeAttribute('aria-busy');}
        });
    });
    const alerts=document.querySelector("[data-admin-alerts]");
    if(alerts){
        let timer=0,loading=false,previous=null;
        const poll=async()=>{
            clearTimeout(timer);if(document.hidden||loading)return;loading=true;
            try{const counts=await fetchJson(alerts.dataset.alertsUrl);for(const key of ["orders","messages","reviews","notifications","total"])document.querySelectorAll(`[data-alert-count="${key}"]`).forEach(e=>{e.textContent=e.classList.contains("shop-alert-badge")&&counts[key]>99?"99+":String(counts[key]);if(e.classList.contains("shop-alert-badge"))e.hidden=counts[key]===0;e.setAttribute("aria-label",`${counts[key]} ${key==="orders"?"đơn chờ xác nhận":key==="messages"?"tin nhắn chưa đọc":key==="reviews"?"đánh giá mới":"thông báo"}`);});if(previous!==null&&counts.total>previous)alerts.querySelector("[data-alert-status]").textContent="Cửa hàng có thông báo mới.";previous=counts.total;}catch{}finally{loading=false;if(!document.hidden)timer=setTimeout(poll,15000);}
        };document.addEventListener("visibilitychange",()=>document.hidden?clearTimeout(timer):poll());poll();
    }

    const chatBubble=(list,text,own,label,at=new Date())=>{
        const bubble=document.createElement('article');bubble.className=`chat-bubble${own?' is-own':''}`;
        const who=document.createElement('strong'),content=document.createElement('p'),time=document.createElement('small');
        who.textContent=label;content.textContent=text;time.textContent=new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'}).format(new Date(at));
        bubble.append(who,content,time);list.append(bubble);return bubble;
    };
    const typingBubble=(list,label)=>{
        const bubble=document.createElement('div');bubble.className='chat-typing';bubble.setAttribute('role','status');bubble.setAttribute('aria-label',label);
        for(let i=0;i<3;i++){const dot=document.createElement('span');dot.setAttribute('aria-hidden','true');bubble.append(dot);}list.append(bubble);return bubble;
    };
    const recoverDraft=(input,text,bubble)=>{
        if(!input.value){input.value=text;bubble.remove();}
        else {bubble.classList.remove('is-sending');bubble.classList.add('is-failed');bubble.querySelector('small').textContent='Chưa gửi · Nội dung được giữ lại ở đây.';}
    };
    // Native pointer capture keeps dragging smooth without intercepting message scrolling.
    const movableChat=(element,handle,key,keyboardHandle,altKey=false)=>{
        let position=null,drag=null,suppressUntil=0;
        try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved&&Number.isFinite(saved.x)&&Number.isFinite(saved.y))position=saved;}catch{}
        const bounds=()=>{const v=window.visualViewport;return {left:v?.offsetLeft||0,top:v?.offsetTop||0,width:v?.width||innerWidth,height:v?.height||innerHeight};};
        const place=()=>{if(!position||!element.getClientRects().length)return;const r=element.getBoundingClientRect(),v=bounds();position={x:Math.max(v.left+8,Math.min(position.x,v.left+v.width-r.width-8)),y:Math.max(v.top+8,Math.min(position.y,v.top+v.height-r.height-8))};element.classList.add('is-positioned');Object.assign(element.style,{left:`${position.x}px`,top:`${position.y}px`,right:'auto',bottom:'auto'});};
        const save=()=>{try{localStorage.setItem(key,JSON.stringify(position));}catch{}};
        const reset=()=>{position=null;element.classList.remove('is-positioned');for(const name of ['left','top','right','bottom'])element.style.removeProperty(name);try{localStorage.removeItem(key);}catch{}};
        handle.addEventListener('pointerdown',event=>{if(!event.isPrimary||event.button!==0)return;const control=event.target.closest('button,a,input,textarea,select');if(control&&control!==element&&!control.matches('[data-chat-drag-handle]'))return;const r=element.getBoundingClientRect();drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:r.left,top:r.top,moved:false};});
        handle.addEventListener('pointermove',event=>{if(!drag||event.pointerId!==drag.id)return;const dx=event.clientX-drag.x,dy=event.clientY-drag.y;if(!drag.moved&&Math.hypot(dx,dy)<6)return;if(!drag.moved){drag.moved=true;handle.setPointerCapture(event.pointerId);element.classList.add('is-dragging');}event.preventDefault();position={x:drag.left+dx,y:drag.top+dy};place();});
        const end=event=>{if(!drag||event.pointerId!==drag.id)return;if(drag.moved){suppressUntil=performance.now()+500;save();}drag=null;element.classList.remove('is-dragging');if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);};
        handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);handle.addEventListener('lostpointercapture',()=>{drag=null;element.classList.remove('is-dragging');});
        handle.addEventListener('click',event=>{if(event.target.closest('[data-hybrid-close]'))return;if(performance.now()<suppressUntil){event.preventDefault();event.stopImmediatePropagation();suppressUntil=0;}},true);
        keyboardHandle.addEventListener('keydown',event=>{if(altKey&&!event.altKey)return;if(event.key==='Home'){event.preventDefault();reset();return;}const offsets={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]},offset=offsets[event.key];if(!offset)return;event.preventDefault();const r=element.getBoundingClientRect(),step=event.shiftKey?32:12;position={x:r.left+offset[0]*step,y:r.top+offset[1]*step};place();save();});
        window.addEventListener('resize',place);window.visualViewport?.addEventListener('resize',place);window.visualViewport?.addEventListener('scroll',place);place();return place;
    };
    const hybrid=document.querySelector('[data-hybrid-chat]');
    if(hybrid){
        const launcher=document.querySelector('[data-hybrid-open]'),tabs=[...hybrid.querySelectorAll('[data-hybrid-tab]')];
        let opener=launcher,preferred='ai';
        try{preferred=sessionStorage.getItem('greenshop.chat.mode')==='store'?'store':'ai';}catch{}
        const activate=mode=>{tabs.forEach(tab=>{const selected=tab.dataset.hybridTab===mode;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;document.getElementById(tab.getAttribute('aria-controls')).hidden=!selected;});preferred=mode;try{sessionStorage.setItem('greenshop.chat.mode',mode);}catch{}hybrid.dispatchEvent(new Event('chatvisible'));};
        const fit=()=>{const viewport=window.visualViewport;hybrid.classList.toggle('is-keyboard',(viewport?.height||innerHeight)<innerHeight-100);hybrid.style.setProperty('--chat-width',`${viewport?.width||innerWidth}px`);hybrid.style.setProperty('--chat-viewport',`${viewport?.height||innerHeight}px`);hybrid.style.setProperty('--chat-keyboard',`${Math.max(0,innerHeight-(viewport?.height||innerHeight)-(viewport?.offsetTop||0))}px`);hybrid.dispatchEvent(new Event('chatlayout'));};
        const dismiss=()=>{hybrid.hidden=true;launcher.setAttribute('aria-expanded','false');opener?.focus({preventScroll:true});};
        const show=(mode,trigger=launcher)=>{opener=trigger;hybrid.hidden=false;launcher.setAttribute('aria-expanded','true');fit();activate(mode==='shop'?'store':mode==='ai'?'ai':preferred);tabs.find(t=>t.getAttribute('aria-selected')==='true').focus({preventScroll:true});};
        document.addEventListener('click',event=>{const trigger=event.target.closest('[data-hybrid-open],[data-chat-mode]');if(!trigger)return;event.preventDefault();if(trigger===launcher&&!hybrid.hidden)dismiss();else show(trigger===launcher?'ai':trigger.dataset.chatMode,trigger);});
        hybrid.querySelector('[data-hybrid-close]').addEventListener('click',dismiss);
        hybrid.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();dismiss();}});
        tabs.forEach((tab,index)=>{tab.addEventListener('click',()=>activate(tab.dataset.hybridTab));tab.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const selected=tabs[event.key==='Home'?0:event.key==='End'?tabs.length-1:(index+(event.key==='ArrowRight'?1:tabs.length-1))%tabs.length];activate(selected.dataset.hybridTab);selected.focus();}});});
        const placePanel=movableChat(hybrid,hybrid.querySelector('header'),'greenshop.chat.position.panel',hybrid.querySelector('[data-chat-drag-handle]'));
        movableChat(launcher,launcher,'greenshop.chat.position.launcher',launcher,true);
        hybrid.addEventListener('chatlayout',placePanel);hybrid.addEventListener('chatvisible',placePanel);
        window.visualViewport?.addEventListener('resize',fit);window.visualViewport?.addEventListener('scroll',fit);window.addEventListener('resize',fit);fit();
        const intent=new URL(location.href);if(['shop','ai'].includes(intent.searchParams.get('chat'))){const mode=intent.searchParams.get('chat');intent.searchParams.delete('chat');history.replaceState(history.state,'',intent.pathname+intent.search+intent.hash);show(mode);}
        const form=hybrid.querySelector('[data-ai-form]'),status=hybrid.querySelector('[data-ai-status]'),list=hybrid.querySelector('[data-ai-messages]'),button=form.querySelector('button'),input=form.elements.Question,reset=hybrid.querySelector('[data-ai-reset]');
        let conversation='',pending=null,available=false,storageKey='',turns=[],identityChanged=false,pendingDraft='';
        button.disabled=true;
        const append=turn=>chatBubble(list,turn.text,turn.role==='user',turn.role==='user'?'Bạn':'Trợ lý AI',turn.at);
        const welcome=()=>{if(!list.children.length){const greeting=chatBubble(list,'Xin chào! Mình là trợ lý của GreenShop. Bạn đang tìm cây, hoa hay một món quà xanh nào?',false,'Trợ lý AI');greeting.dataset.chatWelcome='';}};
        const presence=()=>{hybrid.querySelector('[data-chat-presence]').textContent=preferred==='store'?'Chat với Shop · Tin nhắn trực tiếp':pending?'Trợ lý AI · Đang trả lời':available?'Trợ lý AI · Sẵn sàng tư vấn':'Trợ lý AI · Chưa khả dụng';};
        hybrid.addEventListener('chatvisible',presence);
        hybrid.querySelectorAll('[data-chat-suggestion]').forEach(chip=>chip.addEventListener('click',()=>{input.value=chip.dataset.chatSuggestion;input.focus({preventScroll:true});save();}));
        const save=()=>{if(!storageKey||identityChanged)return;try{sessionStorage.setItem(storageKey,JSON.stringify({expires:Date.now()+1800000,conversation,turns:turns.slice(-8),draft:input.value||pendingDraft}));}catch{}};
        input.addEventListener('input',save);
        hybrid.addEventListener('chatidentitychanged',()=>{identityChanged=true;pending?.abort();conversation='';turns=[];pendingDraft='';list.replaceChildren();input.value='';available=false;button.disabled=true;if(storageKey)try{sessionStorage.removeItem(storageKey);}catch{}status.textContent='Phiên đăng nhập đã thay đổi. Vui lòng tải lại trang.';});
        const restore=()=>{if(!storageKey)return;try{const data=JSON.parse(sessionStorage.getItem(storageKey)||'null');if(!data||data.expires<Date.now()||typeof data.conversation!=='string'||data.conversation.length>65536||!Array.isArray(data.turns)){sessionStorage.removeItem(storageKey);return;}conversation=data.conversation;turns=data.turns.slice(-8).filter(t=>['user','assistant'].includes(t.role)&&typeof t.text==='string'&&t.text.length<=2000&&Number.isFinite(Date.parse(t.at)));turns.forEach(append);if(typeof data.draft==='string')input.value=data.draft.slice(0,1000);}catch{}};
        fetchJson('/TroLy/TrangThai').then(data=>{if(identityChanged)return;available=data.available===true;if(/^[a-f0-9]{64}$/.test(data.session)){storageKey='greenshop.ai.'+data.session;restore();}welcome();presence();status.textContent=available?'Giá và tồn kho hiển thị ở thẻ sản phẩm; kiểm tra lại khi đặt hàng.':'Trợ lý AI hiện chưa khả dụng. Bạn có thể chat với cửa hàng.';button.disabled=!available;}).catch(()=>{presence();status.textContent='Trợ lý AI tạm gián đoạn. Chat với Shop vẫn sẵn sàng.';});
        reset.addEventListener('click',()=>{pending?.abort();pending=null;pendingDraft='';button.disabled=!available;reset.disabled=false;form.removeAttribute('aria-busy');conversation='';turns=[];list.replaceChildren();welcome();save();presence();status.textContent='Đã bắt đầu cuộc trò chuyện mới.';input.focus();});
        window.addEventListener('pagehide',()=>{save();pending?.abort();});
        input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();if(available&&!pending)form.requestSubmit();}});
        form.addEventListener('submit',async event=>{
            event.preventDefault();if(pending||!available||!input.value.trim()||!form.checkValidity())return;button.disabled=true;reset.disabled=true;form.setAttribute('aria-busy','true');status.textContent='Đang hỏi trợ lý…';
            const question=input.value,body=new FormData(form);body.set('Conversation',conversation);const controller=new AbortController();pending=controller;const timeout=setTimeout(()=>controller.abort(),65000);
            list.querySelector('[data-chat-welcome]')?.remove();
            const at=new Date().toISOString(),own=append({role:'user',text:question,at});own.classList.add('is-sending');
            const typing=typingBubble(list,'Trợ lý AI đang trả lời');pendingDraft=question;input.value='';save();presence();list.scrollTop=list.scrollHeight;
            try{
                const data=await fetchJson(form.action,{method:'POST',body,signal:controller.signal});if(pending!==controller||identityChanged)return;conversation=data.conversation||'';
                typing.remove();pendingDraft='';own.classList.remove('is-sending');
                const answer={role:'assistant',text:data.answer,at:new Date().toISOString()};append(answer);turns.push({role:'user',text:question,at},answer);turns=turns.slice(-8);
                for(const product of data.products||[]){
                    if(!Number.isInteger(product.id)||product.link!==`/SanPham/ChiTietSanPham/${product.id}`)continue;
                    const link=document.createElement('a');link.className='hybrid-product';link.href=product.link;
                    const image=document.createElement('img'),fallback='/images/product-placeholder.svg';
                    const imageUrl=typeof product.imageUrl==='string'?product.imageUrl:'';
                    let safeImage=fallback;
                    try{const url=new URL(imageUrl,location.origin);if((imageUrl.startsWith('/uploads/products/')&&!imageUrl.includes('..')&&!imageUrl.includes('\\')&&url.origin===location.origin)||url.protocol==='https:'&&imageUrl.startsWith('https://'))safeImage=url.href;}catch{}
                    image.referrerPolicy='no-referrer';image.alt=product.name;image.width=56;image.height=56;image.addEventListener('error',()=>{if(image.getAttribute('src')!==fallback)image.src=fallback;});image.src=safeImage;
                    const details=document.createElement('span'),name=document.createElement('strong'),price=document.createElement('span'),stock=document.createElement('small'),more=document.createElement('span');
                    name.textContent=product.name;price.textContent=new Intl.NumberFormat('vi-VN',{style:'currency',currency:'VND',maximumFractionDigits:2,minimumFractionDigits:Number.isInteger(product.price)?0:2}).format(product.price);stock.textContent=`Tồn kho: ${product.stockQuantity}`;
                    details.append(name,price,stock);if(product.reviewCount>0){const rating=document.createElement('small');rating.textContent=`${Number(product.rating).toFixed(1)}/5 (${product.reviewCount} đánh giá)`;details.append(rating);}
                    more.className='hybrid-product-more';more.textContent='↗';more.setAttribute('aria-hidden','true');link.setAttribute('aria-label',`Xem sản phẩm ${product.name}`);link.append(image,details,more);list.append(link);
                }
                if(data.policy){const note=document.createElement('p');note.textContent=data.policy;list.append(note);}
                status.textContent='Giá và tồn kho hiển thị ở thẻ sản phẩm; kiểm tra lại khi đặt hàng.';while(list.children.length>32)list.firstElementChild.remove();list.scrollTop=list.scrollHeight;save();
            }catch(error){if(pending!==controller||identityChanged)return;recoverDraft(input,question,own);pendingDraft='';if(error.resetConversation){conversation='';turns=[];}save();status.textContent=error.name==='AbortError'?'Đã dừng chờ trợ lý. Bạn có thể thử lại.':error.message;}
            finally{clearTimeout(timeout);typing.remove();if(pending===controller){pending=null;button.disabled=!available;reset.disabled=false;form.removeAttribute('aria-busy');presence();}}
        });
    }
    document.querySelectorAll("[data-shop-chat]").forEach(chat=>{
    const form=chat.querySelector("[data-chat-form]"),list=chat.querySelector("[data-chat-messages]"),empty=chat.querySelector("[data-chat-empty]"),feedback=chat.querySelector("[data-chat-feedback]"),input=form.elements.Content,button=form.querySelector('[type="submit"]'),admin=chat.dataset.admin==="true";
    let last=0,timer=0,loading=false,sending=false,readThrough=0,joined=0,dirty=false,connectionTimer=0,starting=false,disposed=false,retry=null,sendError=false,canReply=chat.dataset.canReply!=="false";
    const token=()=>form.querySelector('[name="__RequestVerificationToken"]').value;
    const visible=()=>!document.hidden&&chat.getClientRects().length>0;
    const markRead=async()=>{if(disposed||!last||last<=readThrough||!visible())return;await fetchJson(chat.dataset.readUrl,{method:"POST",body:new URLSearchParams({through:String(last),__RequestVerificationToken:token()})});readThrough=last;};
    const connection=new signalR.HubConnectionBuilder().withUrl(admin?"/Admin/supportHub":"/supportHub").withAutomaticReconnect([0,1000,3000,10000]).configureLogging(signalR.LogLevel.None).build();
    const synchronize=async()=>{
        clearTimeout(timer);timer=0;if(disposed||!visible())return;if(loading||sending){dirty=true;return;}loading=true;dirty=false;
        try {
            const data=await fetchJson(`${chat.dataset.messagesUrl}?after=${last}`);
            if(chat.dataset.chatIdentity&&data.identity!==chat.dataset.chatIdentity){disposed=true;chat.dataset.invalidIdentity="true";clearTimeout(connectionTimer);connection.stop();list.replaceChildren();empty.hidden=true;input.value="";input.disabled=true;button.disabled=true;feedback.textContent="Phiên đăng nhập đã thay đổi. Vui lòng tải lại trang.";hybrid?.dispatchEvent(new Event("chatidentitychanged"));return;}
            if(admin){
                canReply=data.canReply===true;button.disabled=disposed||sending||!canReply;
                const labels={Waiting:'Chờ phản hồi',InProgress:'Đang hỗ trợ',Resolved:'Đã giải quyết'};
                const state=document.querySelector('[data-conversation-state]'),hint=document.querySelector('[data-conversation-hint]');
                if(state)state.textContent=labels[data.status]||'Đang cập nhật';
                if(hint)hint.textContent=canReply?(data.status==='Waiting'?'Gửi phản hồi đầu tiên để tự động tiếp nhận cuộc trò chuyện này.':'Bạn đang phụ trách cuộc trò chuyện này.'):data.status==='Resolved'?'Cuộc trò chuyện đã kết thúc. Mở lại để tiếp tục hỗ trợ.':`${data.assignedAdminName||'Quản trị viên khác'} đang phụ trách. Bạn có thể xem tin nhắn tại đây.`;
                document.querySelectorAll('[data-conversation-action]').forEach(action=>{action.hidden=action.dataset.conversationAction==='claim'?!(data.status==='Waiting'&&data.assignedAdminId===null):action.dataset.conversationAction==='resolve'?!(data.status==='InProgress'&&canReply):!data.canReopen;});
                if(Number.isSafeInteger(data.version))document.querySelectorAll('[data-conversation-version]').forEach(field=>field.value=String(data.version));
            }
            if(sending){dirty=true;return;}
            const nearBottom=list.scrollHeight-list.scrollTop-list.clientHeight<80;
            for(const message of data.messages){if(message.id<=last)continue;const bubble=document.createElement("article");bubble.className=`chat-bubble${message.fromAdmin===admin?" is-own":""}`;bubble.dataset.messageId=String(message.id);const who=document.createElement("strong"),text=document.createElement("p"),time=document.createElement("small");who.textContent=message.fromAdmin?"GreenShop":"Khách hàng";text.textContent=message.content;time.textContent=new Intl.DateTimeFormat("vi-VN",{timeZone:"Asia/Ho_Chi_Minh",hour:"2-digit",minute:"2-digit"}).format(new Date(message.createdAt+(/Z$|[+-]\d\d:\d\d$/.test(message.createdAt)?"":"Z")));bubble.append(who,text,time);list.append(bubble);last=message.id;}
            empty.hidden=last>0;if(!last)empty.textContent="Gửi lời chào để bắt đầu. Cửa hàng sẽ tiếp nhận và trả lời bạn.";if(nearBottom)list.scrollTop=list.scrollHeight;
            if(nearBottom)await markRead();if(!sending&&!sendError)feedback.textContent="";
            if(data.conversationId&&connection.state===signalR.HubConnectionState.Connected&&joined!==data.conversationId){await connection.invoke("JoinConversation",data.conversationId);joined=data.conversationId;dirty=true;}
            if(data.hasMore)dirty=true;
        } catch(error){feedback.textContent=error.message;} finally {loading=false;if(dirty)timer=setTimeout(synchronize,0);else if(!disposed&&visible())timer=setTimeout(synchronize,30000);}
    };
    connection.on("Changed",()=>synchronize());
    connection.onreconnected(()=>{joined=0;chat.dataset.realtime="connected";synchronize();});
    connection.onreconnecting(()=>{chat.dataset.realtime="reconnecting";feedback.textContent="Đang kết nối lại…";});
    const start=async()=>{if(disposed||starting||!visible()||connection.state!==signalR.HubConnectionState.Disconnected)return;starting=true;clearTimeout(connectionTimer);try{await connection.start();joined=0;chat.dataset.realtime="connected";await synchronize();}catch{chat.dataset.realtime="disconnected";if(!disposed&&visible())connectionTimer=setTimeout(start,5000);}finally{starting=false;}};
    connection.onclose(()=>{if(!disposed&&visible())connectionTimer=setTimeout(start,5000);});start();
    form.addEventListener("submit",async e=>{
        e.preventDefault();if(disposed||sending||!canReply||!input.value.trim()||!form.checkValidity())return;sendError=false;sending=true;button.disabled=true;form.setAttribute("aria-busy","true");feedback.textContent="Đang gửi…";const sent=input.value;
        // Retry an uncertain request with the same token only for the same content.
        form.elements.RequestToken.value=retry?.text===sent?retry.token:crypto.randomUUID().replaceAll('-','');
        const body=new FormData(form),own=chatBubble(list,sent,true,admin?'GreenShop':'Bạn');own.classList.add('is-sending');empty.hidden=true;input.value='';list.scrollTop=list.scrollHeight;
        try{const data=await fetchJson(form.action,{method:"POST",body});if(disposed)return;own.dataset.messageId=String(data.id);own.classList.remove('is-sending');retry=null;feedback.textContent="Đã gửi tin nhắn.";}
        catch(error){if(!disposed){sendError=true;retry={text:sent,token:body.get('RequestToken')};recoverDraft(input,sent,own);feedback.textContent=error.message;}}
        finally{sending=false;form.removeAttribute("aria-busy");if(!disposed){button.disabled=!canReply;if(own.dataset.messageId)own.remove();await synchronize();if(visible()&&form.contains(document.activeElement))input.focus({preventScroll:true});}}
    });
    input.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey&&!e.isComposing){e.preventDefault();form.requestSubmit();}});
    list.addEventListener("scroll",()=>{if(list.scrollHeight-list.scrollTop-list.clientHeight<80)markRead().catch(()=>{});},{passive:true});
    document.addEventListener("visibilitychange",()=>{if(document.hidden)clearTimeout(timer);else {if(connection.state===signalR.HubConnectionState.Disconnected)start();synchronize();}});
    hybrid?.addEventListener("chatvisible",()=>{start();synchronize();});window.addEventListener("pagehide",()=>{disposed=true;clearTimeout(timer);clearTimeout(connectionTimer);connection.stop();});window.addEventListener("pageshow",event=>{if(!event.persisted)return;disposed=chat.dataset.invalidIdentity==="true";if(!disposed){start();synchronize();}});synchronize();
    });
})();
