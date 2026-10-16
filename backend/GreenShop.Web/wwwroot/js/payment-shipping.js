(() => {
    'use strict';
    const cents=value=>{
        const match=String(value).match(/^(\d+)(?:\.(\d{1,2}))?$/);
        return match ? BigInt(match[1])*100n+BigInt((match[2]||'').padEnd(2,'0')) : null;
    };
    const money=value=>new Intl.NumberFormat('vi-VN').format(value/100n)+(value%100n ? ','+String(value%100n).padStart(2,'0') : '')+' đ';
    const checkout=document.querySelector('[data-shipping-preview]');
    function updateCheckout(){
        if(!checkout)return;
        const quantity=Number(document.querySelector('#Quantity').value);
        const price=cents(checkout.dataset.price),fixed=cents(checkout.dataset.flatFee),threshold=cents(checkout.dataset.freeThreshold);
        const subtotal=checkout.dataset.cartSubtotal ? cents(checkout.dataset.cartSubtotal) : Number.isInteger(quantity)&&quantity>=1&&quantity<=1000000&&price!==null ? price*BigInt(quantity) : null;
        if(subtotal===null || fixed===null || threshold===null)return;
        const fee=subtotal>=threshold ? 0n : fixed;
        checkout.querySelector('[data-payment-subtotal]').textContent=money(subtotal);
        checkout.querySelector('[data-payment-shipping]').textContent=money(fee);
        checkout.querySelector('[data-payment-total]').textContent=money(subtotal+fee);
        checkout.querySelector('[data-shipping-message]').textContent=subtotal>=threshold ? 'Đơn hàng của bạn được miễn phí vận chuyển.' : 'Mua thêm '+money(threshold-subtotal)+' để được miễn phí vận chuyển.';
        checkout.querySelector('[data-shipping-progress]').style.width=(threshold===0n ? 100 : Number(subtotal*100n/threshold>100n ? 100n : subtotal*100n/threshold))+'%';
        if(!checkout.dataset.cartSubtotal)checkout.querySelector('[data-checkout-quantity]').textContent=String(quantity);
    }
    document.addEventListener('input',event=>{
        if(event.target.id==='Quantity')updateCheckout();
        if(event.target.matches('[data-bank-search]')){
            const term=event.target.value.trim().toLocaleLowerCase('vi');
            document.querySelectorAll('#Bank_BankBin option').forEach(option=>{option.hidden=!!option.value&&!option.selected&&!option.textContent.toLocaleLowerCase('vi').includes(term);});
        }
    });
    document.addEventListener('change',event=>{
        if(event.target.name==='PaymentMethod')document.querySelector('[data-method-note]').textContent=event.target.value==='VIETQR' ? 'Sau khi đặt hàng, GreenShop sẽ hiển thị mã QR để bạn chuyển khoản.' : 'Bạn sẽ thanh toán khi nhận được hàng.';
    });
    updateCheckout();
    const example=document.querySelector('[data-shipping-example]');
    function updateExample(){
        if(!example)return;
        const price=cents(document.querySelector('#shippingExample').value),fee=cents(document.querySelector('#Shipping_FlatShippingFee').value),threshold=cents(document.querySelector('#Shipping_FreeShippingThreshold').value);
        if(price===null || fee===null || threshold===null){example.querySelector('[data-example-fee]').textContent='Kiểm tra số tiền';example.querySelector('[data-example-total]').textContent='—';return;}
        const charge=price>=threshold ? 0n : fee;
        example.querySelector('[data-example-fee]').textContent=money(charge);example.querySelector('[data-example-total]').textContent=money(price+charge);
    }
    example?.addEventListener('input',updateExample);updateExample();
    function imageState(img){
        const shell=img.closest('[data-qr-shell]');if(!shell)return;
        const failed=img.complete&&img.naturalWidth===0;
        shell.querySelector('[data-qr-loading]').hidden=img.complete;
        shell.querySelector('[data-qr-error]').hidden=!failed;
        img.hidden=failed;
        shell.classList.toggle('is-loaded',img.complete&&!failed);
    }
    document.querySelectorAll('[data-vietqr-image]').forEach(img=>{img.addEventListener('load',()=>imageState(img));img.addEventListener('error',()=>imageState(img));if(img.complete)imageState(img);});
    document.addEventListener('click',async event=>{
        const button=event.target.closest('[data-copy-value]');if(!button)return;
        const feedback=document.querySelector('.payment-copy-feedback');
        const value=button.dataset.copyValue;if(!value)return;
        try{
            if(navigator.clipboard&&isSecureContext)await navigator.clipboard.writeText(value);
            else{
                const field=document.createElement('textarea');field.value=value;field.style.position='fixed';field.style.left='-9999px';document.body.append(field);
                try{field.select();if(!document.execCommand('copy'))throw new Error('Clipboard unavailable');}finally{field.remove();button.focus({preventScroll:true});}
            }
            if(feedback)feedback.textContent='Đã sao chép. Kiểm tra thông tin trong ứng dụng ngân hàng trước khi chuyển.';
            button.classList.add('is-copied');setTimeout(()=>button.classList.remove('is-copied'),1600);
        }catch{if(feedback)feedback.textContent='Chưa thể sao chép tự động. Bạn có thể chọn và sao chép thông tin hiển thị.';}
    });
    document.querySelectorAll('[data-settings-submit]').forEach(form=>form.addEventListener('submit',event=>{
        if(form.dataset.busy==='true'){event.preventDefault();return;}
        if(!form.checkValidity())return;
        form.dataset.busy='true';form.setAttribute('aria-busy','true');
        form.querySelectorAll('button[type=submit]').forEach(button=>{button.dataset.original=button.innerHTML;button.disabled=true;button.textContent='Đang lưu…';});
    }));
    addEventListener('pageshow',()=>document.querySelectorAll('[data-settings-submit][data-busy=true]').forEach(form=>{
        delete form.dataset.busy;form.removeAttribute('aria-busy');form.querySelectorAll('button[type=submit]').forEach(button=>{button.disabled=false;button.innerHTML=button.dataset.original;});
    }));
})();
