using System.Data;
using System.Data.Common;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Controllers;

[Authorize(Roles = "Customer")]
public class GioHangController(AppDbContext db, ILogger<GioHangController> logger) : Controller
{
    [HttpGet]
    public async Task<IActionResult> QuanLyGioHang(CancellationToken ct)
    {
        var userId = ShoppingIdentity.UserId(User);
        if (userId == 0) return Forbid();
        var items = await db.CartItems.AsNoTracking().Where(i => i.UserId == userId).OrderByDescending(i => i.Id)
            .Select(i => new CartRowViewModel
            {
                Id = i.Id, Quantity = i.Quantity, Available = i.Product.CategoryId == null || i.Product.Category!.IsActive,
                Product = new StoreProductViewModel
                {
                    Id = i.ProductId, Name = i.Product.Name, ImageUrl = i.Product.ImageUrl, Price = i.Product.Price,
                    StockQuantity = i.Product.StockQuantity, CategoryId = i.Product.CategoryId,
                    CategoryName = i.Product.Category == null ? "Chưa phân loại" : i.Product.Category.Name
                }
            }).ToListAsync(ct);
        return View(new CartViewModel { Items = items });
    }

    [AllowAnonymous, HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> ThemVaoGioHang([FromRoute] int id, QuantityViewModel model, CancellationToken ct)
    {
        if(User.IsInRole("Admin"))return Forbid();
        if (User.Identity?.IsAuthenticated != true)
            return RedirectToAction("Login", "Account", new { returnUrl = Url.Action("ChiTietSanPham", "SanPham", new { id }) });
        var userId = ShoppingIdentity.UserId(User);
        if (userId == 0) return Forbid();
        if (!ModelState.IsValid || id <= 0)
        {
            TempData["ErrorMessage"] = "Số lượng phải là số nguyên dương, tối đa 1.000.000.";
            return RedirectToAction("ChiTietSanPham", "SanPham", new { id });
        }
        var error = await WriteQuantityAsync(userId, id, model.Quantity, null, ct);
        TempData[error == null ? "SuccessMessage" : "ErrorMessage"] = error ?? "Đã thêm sản phẩm vào giỏ hàng của bạn.";
        return RedirectToAction(nameof(QuanLyGioHang));
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> CapNhatSoLuong([FromRoute] int id, QuantityViewModel model, CancellationToken ct)
    {
        var userId = ShoppingIdentity.UserId(User);
        if (userId == 0) return Forbid();
        var item = await db.CartItems.AsNoTracking().FirstOrDefaultAsync(i => i.Id == id && i.UserId == userId, ct);
        if (item == null) return NotFound();
        var error = !ModelState.IsValid ? "Số lượng phải là số nguyên dương, tối đa 1.000.000." : await WriteQuantityAsync(userId, item.ProductId, model.Quantity, id, ct);
        TempData[error == null ? "SuccessMessage" : "ErrorMessage"] = error ?? "Đã cập nhật số lượng.";
        return RedirectToAction(nameof(QuanLyGioHang));
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> XoaKhoiGioHang([FromRoute] int id, CancellationToken ct)
    {
        var userId = ShoppingIdentity.UserId(User);
        if (userId == 0) return Forbid();
        var removed=await db.Database.CreateExecutionStrategy().ExecuteAsync(async()=>
        {
            await using var transaction=await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted,ct);
            var actor=await ShoppingIdentity.LockUserAsync(db,userId,ct);
            if(actor==null || !actor.IsActive || actor.Role!=UserRole.Customer || actor.SessionVersion!=UserSession.Version(User)) return -1;
            var count=await db.CartItems.Where(i=>i.Id==id && i.UserId==userId).ExecuteDeleteAsync(ct);
            await transaction.CommitAsync(ct);return count;
        });
        if(removed<0) return Forbid();if(removed==0) return NotFound();
        TempData["SuccessMessage"] = "Đã xóa sản phẩm khỏi giỏ hàng.";
        return RedirectToAction(nameof(QuanLyGioHang));
    }

    private async Task<string?> WriteQuantityAsync(int userId, int productId, int quantity, int? itemId, CancellationToken ct)
    {
        try
        {
            return await db.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
            {
                db.ChangeTracker.Clear();
                await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
                var actor=await ShoppingIdentity.LockUserAsync(db,userId,ct);
                if(actor==null || !actor.IsActive || actor.Role!=UserRole.Customer || actor.SessionVersion!=UserSession.Version(User))
                    return "Phiên mua hàng không còn hợp lệ.";
                var product = (await db.Products.FromSqlInterpolated($"SELECT * FROM Products WHERE Id = {productId} FOR UPDATE").AsNoTracking().ToListAsync(ct)).SingleOrDefault();
                if (product == null || (product.CategoryId.HasValue && !await db.Categories.AnyAsync(c => c.Id == product.CategoryId && c.IsActive, ct))) return "Sản phẩm không còn được bán.";
                var item = await db.CartItems.SingleOrDefaultAsync(i => i.UserId == userId && i.ProductId == productId, ct);
                if (itemId.HasValue && item?.Id != itemId) return "Mục giỏ hàng không còn tồn tại.";
                var total = itemId.HasValue ? quantity : (long)(item?.Quantity ?? 0) + quantity;
                if (total <= 0 || total > product.StockQuantity || total > 1_000_000) return "Số lượng yêu cầu vượt tồn kho hoặc giới hạn cho phép. Vui lòng chọn lại.";
                if (item == null) db.CartItems.Add(new CartItem { UserId = userId, ProductId = productId, Quantity = (int)total });
                else item.Quantity = (int)total;
                await db.SaveChangesAsync(ct);
                await transaction.CommitAsync(ct);
                return null;
            });
        }
        catch (Exception ex) when (ex is DbException or DbUpdateException)
        {
            logger.LogError(ex, "Không thể cập nhật giỏ hàng.");
            return "Chưa thể lưu giỏ hàng. Vui lòng thử lại.";
        }
    }
}
