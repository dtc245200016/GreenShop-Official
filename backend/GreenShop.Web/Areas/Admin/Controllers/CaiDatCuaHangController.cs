using System.Data.Common;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Areas.Admin.Controllers;

[Area("Admin"),Authorize(Roles="Admin")]
public class CaiDatCuaHangController(AppDbContext db,ILogger<CaiDatCuaHangController> logger) : Controller
{
    [HttpGet,ResponseCache(NoStore=true,Location=ResponseCacheLocation.None)]
    public async Task<IActionResult> QuanLyThanhToanVanChuyen(CancellationToken ct)
    {
        await VietQrBanks.RefreshAsync(ct);
        try{return View(await ModelAsync(ct));}
        catch(Exception ex) when(ex is DbException or Microsoft.EntityFrameworkCore.Storage.RetryLimitExceededException or InvalidOperationException)
        {
            logger.LogWarning("Chưa thể tải cấu hình thanh toán và vận chuyển.");Response.StatusCode=503;ViewData["Unavailable"]=true;
            return View(new PaymentShippingSettingsViewModel());
        }
    }
    [HttpPost,ValidateAntiForgeryToken]
    public async Task<IActionResult> LuuTaiKhoanNganHang([Bind(Prefix="Bank")] BankSettingsForm form,CancellationToken ct)
    {
        form.BankBin=form.BankBin?.Trim()??"";form.AccountNumber=form.AccountNumber?.Trim()??"";form.AccountHolderName=form.AccountHolderName?.Trim()??"";
        if(VietQrBanks.Find(form.BankBin)==null) ModelState.AddModelError("Bank.BankBin","Vui lòng chọn ngân hàng được VietQR hỗ trợ.");
        if(form.AccountHolderName.Any(char.IsControl)) ModelState.AddModelError("Bank.AccountHolderName","Tên chủ tài khoản không được chứa ký tự điều khiển.");
        if(form.VietQrEnabled && !form.BankDetailsChecked) ModelState.AddModelError("Bank.BankDetailsChecked","Hãy kiểm tra lại thông tin ngân hàng và xác nhận trước khi bật VietQR.");
        if(!ModelState.IsValid) return await InvalidAsync(form,null,400,ct);
        return await SaveAsync(form.ExpectedVersion,async(token)=>await db.PaymentShippingSettings.Where(s=>s.Id==1 && s.Version==form.ExpectedVersion)
            .ExecuteUpdateAsync(s=>s.SetProperty(x=>x.BankBin,form.BankBin).SetProperty(x=>x.BankName,VietQrBanks.Find(form.BankBin)!.Name)
                .SetProperty(x=>x.AccountNumber,form.AccountNumber).SetProperty(x=>x.AccountHolderName,form.AccountHolderName).SetProperty(x=>x.VietQrEnabled,form.VietQrEnabled)
                .SetProperty(x=>x.UpdatedAt,DateTime.UtcNow).SetProperty(x=>x.Version,x=>x.Version+1),token),form,null,ct);
    }
    [HttpPost,ValidateAntiForgeryToken]
    public async Task<IActionResult> LuuChinhSachVanChuyen([Bind(Prefix="Shipping")] ShippingSettingsForm form,CancellationToken ct)
    {
        if(form.FlatShippingFee!=decimal.Truncate(form.FlatShippingFee)) ModelState.AddModelError("Shipping.FlatShippingFee","Phí vận chuyển phải là số VNĐ nguyên.");
        if(form.FreeShippingThreshold!=decimal.Truncate(form.FreeShippingThreshold)) ModelState.AddModelError("Shipping.FreeShippingThreshold","Ngưỡng miễn phí phải là số VNĐ nguyên.");
        if(!ModelState.IsValid) return await InvalidAsync(null,form,400,ct);
        return await SaveAsync(form.ExpectedVersion,async(token)=>await db.PaymentShippingSettings.Where(s=>s.Id==1 && s.Version==form.ExpectedVersion)
            .ExecuteUpdateAsync(s=>s.SetProperty(x=>x.FlatShippingFee,form.FlatShippingFee).SetProperty(x=>x.FreeShippingThreshold,form.FreeShippingThreshold)
                .SetProperty(x=>x.UpdatedAt,DateTime.UtcNow).SetProperty(x=>x.Version,x=>x.Version+1),token),null,form,ct);
    }
    private async Task<IActionResult> SaveAsync(long version,Func<CancellationToken,Task<int>> update,BankSettingsForm? bank,ShippingSettingsForm? shipping,CancellationToken ct)
    {
        try
        {
            var result=await db.Database.CreateExecutionStrategy().ExecuteAsync(async()=>
            {
                await using var transaction=await db.Database.BeginTransactionAsync(System.Data.IsolationLevel.ReadCommitted,ct);
                var actor=await ShoppingIdentity.LockUserAsync(db,ShoppingIdentity.UserId(User),ct);
                if(actor==null || !actor.IsActive || actor.Role!=UserRole.Admin || actor.SessionVersion!=UserSession.Version(User)) return 403;
                if(version==long.MaxValue || await update(ct)!=1) return 409;
                await transaction.CommitAsync(ct);return 200;
            });
            if(result==403) return Forbid();
            if(result==409) {ModelState.AddModelError("","Cấu hình đã thay đổi. Vui lòng tải lại trang và đối chiếu trước khi lưu.");return await InvalidAsync(bank,shipping,409,ct);}
            TempData["SuccessMessage"]=bank!=null ? "Đã lưu tài khoản nhận tiền. Chỉ áp dụng cho các đơn mới." : "Đã lưu chính sách vận chuyển. Phí ship của đơn đã đặt được giữ nguyên.";
            return RedirectToAction(nameof(QuanLyThanhToanVanChuyen));
        }
        catch(Exception ex) when(ex is DbException or DbUpdateException or Microsoft.EntityFrameworkCore.Storage.RetryLimitExceededException)
        {
            logger.LogWarning("Chưa thể lưu cấu hình thanh toán hoặc vận chuyển.");Response.StatusCode=503;ViewData["Unavailable"]=true;
            ModelState.AddModelError("","Chưa thể lưu cấu hình. Vui lòng tải lại để kiểm tra trước khi thử lại.");
            return View("QuanLyThanhToanVanChuyen",new PaymentShippingSettingsViewModel());
        }
    }
    private async Task<IActionResult> InvalidAsync(BankSettingsForm? bank,ShippingSettingsForm? shipping,int status,CancellationToken ct)
    {
        var model=await ModelAsync(ct);if(bank!=null) model.Bank=bank;if(shipping!=null) model.Shipping=shipping;Response.StatusCode=status;
        return View("QuanLyThanhToanVanChuyen",model);
    }
    private async Task<PaymentShippingSettingsViewModel> ModelAsync(CancellationToken ct)
    {
        var s=await db.PaymentShippingSettings.AsNoTracking().SingleAsync(x=>x.Id==1,ct);
        var count=await db.Orders.AsNoTracking().CountAsync(o=>o.PaymentMethod==PaymentMethods.VietQr && !o.IsPaid && o.Status!=OrderStatus.Cancelled &&
            (o.BankBinSnapshot!=s.BankBin || o.BankAccountSnapshot!=s.AccountNumber || o.BankHolderSnapshot!=s.AccountHolderName),ct);
        return new(){Settings=s,Bank=new(){ExpectedVersion=s.Version,BankBin=s.BankBin,AccountNumber=s.AccountNumber,AccountHolderName=s.AccountHolderName,VietQrEnabled=s.VietQrEnabled},
            Shipping=new(){ExpectedVersion=s.Version,FlatShippingFee=s.FlatShippingFee,FreeShippingThreshold=s.FreeShippingThreshold},PendingEarlierBankOrders=count};
    }
}
