/* Progressive enhancement: the href is also a genuine read-only download endpoint. */
(() => {
    'use strict';
    let busy=false;
    const feedback=document.querySelector('.excel-feedback');
    function notify(message,error=false){
        if(!feedback)return;
        feedback.textContent=message;feedback.classList.toggle('is-error',error);feedback.hidden=false;
    }
    document.addEventListener('click',async event=>{
        const button=event.target.closest('a[data-excel-export]');
        if(!button || event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)return;
        event.preventDefault();
        if(busy)return;
        busy=true;
        const label=button.querySelector('span');const oldLabel=label.textContent;
        const abort=new AbortController();const timer=setTimeout(()=>abort.abort(),120000);
        button.setAttribute('aria-busy','true');button.setAttribute('aria-disabled','true');label.textContent='Đang chuẩn bị file...';
        notify('Đang chuẩn bị file Excel theo bộ lọc đã áp dụng…');
        try{
            const response=await fetch(button.href,{credentials:'same-origin',headers:{Accept:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/json'},signal:abort.signal,cache:'no-store'});
            if(response.redirected)throw new Error('Phiên đăng nhập hoặc quyền truy cập đã thay đổi. Vui lòng tải lại trang và đăng nhập nếu cần.');
            if(!response.ok){
                let message='Không thể tạo file Excel. Vui lòng thử lại.';
                if((response.headers.get('content-type')||'').includes('application/json'))message=(await response.json()).message||message;
                else if(response.status===401 || response.status===403)message='Bạn không có quyền xuất báo cáo. Vui lòng tải lại trang.';
                throw new Error(message);
            }
            if(!(response.headers.get('content-type')||'').startsWith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'))throw new Error('Phản hồi không phải file Excel. Vui lòng tải lại trang.');
            const disposition=response.headers.get('content-disposition')||'';
            const encoded=disposition.match(/filename\*=UTF-8''([^;]+)/i);const plain=disposition.match(/filename="?([^";]+)"?/i);
            const name=encoded ? decodeURIComponent(encoded[1]) : plain ? plain[1] : 'GreenShop_BaoCao.xlsx';
            if(!/^GreenShop_[A-Za-z0-9_-]+\.xlsx$/.test(name))throw new Error('Tên file báo cáo không hợp lệ.');
            const blob=await response.blob();
            if(blob.size===0)throw new Error('File báo cáo trống. Vui lòng thử lại.');
            const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);
            try{link.click();notify('File Excel đã sẵn sàng và đã gửi yêu cầu tải xuống trình duyệt.');}
            finally{link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
        }catch(error){notify(error.name==='AbortError' ? 'Quá thời gian chuẩn bị file. Vui lòng thu hẹp bộ lọc rồi thử lại.' : error.name==='TypeError' ? 'Không thể kết nối để tải file Excel. Vui lòng kiểm tra kết nối rồi thử lại.' : error.message,true);}
        finally{clearTimeout(timer);busy=false;label.textContent=oldLabel;button.removeAttribute('aria-busy');button.removeAttribute('aria-disabled');}
    });
})();
