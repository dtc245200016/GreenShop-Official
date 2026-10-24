using System.Data;
using System.Data.Common;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Controllers;

[Authorize(Roles = "Customer")]
public class ThanhToanController(AppDbContext db, ILogger<ThanhToanController> logger, IDataProtectionProvider protection) : Controller
{
    [AllowAnonymous, HttpPost, ValidateAntiForgeryToken]
    public IActionResult MuaNgay([FromRoute] int id, QuantityViewModel model)
    {
        if(User.IsInRole("Admin"))return Forbid();
        var quantity = ModelState.IsValid ? model.Quantity : 1;
        var destination = Url.Action(nameof(XacNhanMuaHang), new { id, quantity });
        if (User.Identity?.IsAuthenticated != true) return RedirectToAction("Login", "Account", new { returnUrl = destination });
        if (!ModelState.IsValid || id <= 0)
        {
            TempData["ErrorMessage"] = "Số lượng phải là số nguyên dương, tối đa 1.000.000.";
            return RedirectToAction("ChiTietSanPham", "SanPham", new { id });
        }
        return Redirect(destination!);
    }

    [HttpGet]
    public async Task<IActionResult> XacNhanMuaHang([FromRoute] int id, int quantity = 1, CancellationToken ct = default)
    {
        if (!ModelState.IsValid || quantity < 1 || quantity > 1_000_000) return BadRequest();
        var model=await PrepareAsync(new CheckoutViewModel {Quantity=quantity,ConfirmationToken=Guid.NewGuid().ToString("N")},id,ct);
        return model==null ? NotFound() : View(model);
    }

    [HttpGet]
    public async Task<IActionResult> XacNhanGioHang(CancellationToken ct)
    {
        var model=await PrepareAsync(new CheckoutViewModel {Quantity=1,ConfirmationToken=Guid.NewGuid().ToString("N")},null,ct);
        if(model==null) {TempData["ErrorMessage"]="Giỏ hàng đang trống. Hãy chọn sản phẩm trước khi thanh toán.";return RedirectToAction("QuanLyGioHang","GioHang");}
        return View("XacNhanMuaHang",model);
    }

    [HttpPost,ValidateAntiForgeryToken]
    public Task<IActionResult> XacNhanMuaHang([FromRoute] int id,CheckoutViewModel model,CancellationToken ct) => PlaceAsync(id,model,ct);

    [HttpPost,ValidateAntiForgeryToken]
    public Task<IActionResult> XacNhanGioHang(CheckoutViewModel model,CancellationToken ct) => PlaceAsync(null,model,ct);

    private async Task<IActionResult> PlaceAsync(int? id,CheckoutViewModel model,CancellationToken ct)
    {
        var userId=ShoppingIdentity.UserId(User);if(userId==0) return Forbid();
        try
        {
            if(ModelState.IsValid)
            {
                var result=await new CheckoutOrders(db,protection).CreateAsync(userId,UserSession.Version(User),id,model,ct);
                if(result.StatusCode==403) return Forbid();
                if(result.OrderId>0)
                {
                    if(result.Created) Observability.BusinessCreated(logger, HttpContext, "order.created");
                    var method=await db.Orders.AsNoTracking().Where(o=>o.Id==result.OrderId && o.UserId==userId).Select(o=>o.PaymentMethod).SingleAsync(ct);
                    TempData["SuccessMessage"]=method==PaymentMethods.VietQr ? "Đã tạo đơn hàng. Quét mã để chuyển khoản; GreenShop sẽ xác nhận sau khi đối chiếu." : "Đã nhận đơn hàng COD. Đơn đang chờ xử lý, chưa thanh toán.";
                    return RedirectToAction(method==PaymentMethods.VietQr ? nameof(ThanhToanVietQR) : nameof(ChiTietDonHang),new {id=result.OrderId});
                }
                ModelState.AddModelError("",result.Message);
            }
            var prepared=await PrepareAsync(model,id,ct);
            if(prepared==null && !id.HasValue)
            {
                TempData["ErrorMessage"]="Giỏ hàng đang trống. Hãy chọn sản phẩm trước khi thanh toán.";
                return RedirectToAction("QuanLyGioHang","GioHang");
            }
            model=prepared ?? model;
            if(model.Product.Id==0 && !model.FromCart) return NotFound();
            return View("XacNhanMuaHang",model);
        }
        catch(Exception ex) when(ex is DbException or DbUpdateException or Microsoft.EntityFrameworkCore.Storage.RetryLimitExceededException)
        {
            logger.LogWarning("Chưa thể lưu đơn hàng hoặc đọc chính sách thanh toán.");
            TempData["ErrorMessage"]="Chưa thể hoàn tất đặt hàng. Vui lòng kiểm tra đơn hàng đã được lưu trước khi thử lại.";
            return RedirectToAction(nameof(DonHangCuaToi));
        }
    }

    private async Task<CheckoutViewModel?> PrepareAsync(CheckoutViewModel model,int? id,CancellationToken ct)
    {
        var userId=ShoppingIdentity.UserId(User);
        var user=await db.Users.AsNoTracking().FirstOrDefaultAsync(u=>u.Id==userId,ct);if(user==null) return null;
        var orders=new CheckoutOrders(db,protection);model.Policy=await orders.SettingsAsync(ct);model.PolicyVersion=model.Policy.Version;
        ModelState.Remove(nameof(model.PolicyVersion));model.FromCart=!id.HasValue;
        if(id.HasValue)
        {
            var product=await GetProductAsync(id.Value,ct);if(product==null) return null;
            model.Product=product;model.QuotedPrice=product.Price;ModelState.Remove(nameof(model.QuotedPrice));
            if(model.Quantity<1 || model.Quantity>1000000) model.Quantity=1;
            model.Lines=new[]{new CheckoutLine(product.Id,product.Name,product.ImageUrl,product.Price,model.Quantity,product.StockQuantity)};
            if(model.Quantity>product.StockQuantity) ModelState.AddModelError(nameof(model.Quantity),"Số lượng vượt tồn kho hiện tại.");
        }
        else
        {
            model.Lines=await orders.CartAsync(userId,ct);if(model.Lines.Count==0) return null;
            model.QuotedPrice=model.Lines[0].Price;model.Quantity=1;model.CartQuote=orders.QuoteCart(userId,model.Lines);
            ModelState.Remove(nameof(model.QuotedPrice));ModelState.Remove(nameof(model.CartQuote));
            if(model.Lines.Any(i=>i.Quantity>i.StockQuantity || i.Quantity<1) || model.Lines.Count>100) ModelState.AddModelError("","Giỏ hàng có mục vượt tồn kho, ngừng bán hoặc quá 100 loại sản phẩm. Vui lòng điều chỉnh.");
        }
        if(string.IsNullOrEmpty(model.RecipientName)) model.RecipientName=user.FullName;
        if(string.IsNullOrEmpty(model.Phone)) model.Phone=user.Phone;
        return model;
    }

    [HttpGet,ResponseCache(NoStore=true,Location=ResponseCacheLocation.None)]
    public async Task<IActionResult> ThanhToanVietQR([FromRoute] int id,CancellationToken ct)
    {
        var userId=ShoppingIdentity.UserId(User);if(userId==0) return Forbid();
        var order=await db.Orders.AsNoTracking().Include(o=>o.Items).FirstOrDefaultAsync(o=>o.Id==id && o.UserId==userId,ct);
        return order==null || order.PaymentMethod!=PaymentMethods.VietQr ? NotFound() : View(order);
    }

    [HttpPost,ValidateAntiForgeryToken]
    public async Task<IActionResult> ThongBaoDaChuyenKhoan([FromRoute] int id,AdminOrderCommand model,CancellationToken ct)
    {
        if(!ModelState.IsValid || id<=0) return BadRequest();
        var result=await new CustomerTransfers(db).NotifyAsync(id,ShoppingIdentity.UserId(User),model.ExpectedVersion,UserSession.Version(User),ct);
        if(result.StatusCode==404) return NotFound();if(result.StatusCode==403) return Forbid();
        TempData[result.StatusCode==200 ? "SuccessMessage" : "ErrorMessage"]=result.Message;
        return RedirectToAction(nameof(ThanhToanVietQR),new {id});
    }

    [HttpGet]
    public async Task<IActionResult> DonHangCuaToi(int page = 1, CancellationToken ct = default)
    {
        if (!ModelState.IsValid || page <= 0) return BadRequest();
        var userId = ShoppingIdentity.UserId(User);
        if (userId == 0) return Forbid();
        var query = db.Orders.AsNoTracking().Where(o => o.UserId == userId);
        var total = await query.CountAsync(ct);
        page = Math.Min(page, Math.Max(1, (int)Math.Ceiling(total / 10d)));
        ViewData["Page"] = page;
        ViewData["TotalPages"] = Math.Max(1, (int)Math.Ceiling(total / 10d));
        return View(await query.OrderByDescending(o => o.Id).Skip((page - 1) * 10).Take(10).ToListAsync(ct));
    }

    [HttpGet]
    public async Task<IActionResult> ChiTietDonHang([FromRoute] int id, CancellationToken ct)
    {
        var userId = ShoppingIdentity.UserId(User);
        if (userId == 0) return Forbid();
        var order = await db.Orders.AsNoTracking().Include(o => o.Items).FirstOrDefaultAsync(o => o.Id == id && o.UserId == userId, ct);
        if(order==null) return NotFound();
        ViewData["ReviewedItems"]=await db.OrderItems.Where(i=>i.OrderId==id && db.ProductReviews.Any(r=>r.UserId==userId && r.OrderItem.OrderId==id && (r.OrderItemId==i.Id || r.ProductId!=null && r.ProductId==i.ProductId))).Select(i=>i.Id).ToListAsync(ct);
        return View(order);
    }

    private Task<StoreProductViewModel?> GetProductAsync(int id, CancellationToken ct) =>
        StoreCatalog.Project(StoreCatalog.Saleable(db).Where(p => p.Id == id), db).FirstOrDefaultAsync(ct);
}
