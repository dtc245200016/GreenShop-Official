using GreenShop.Web.Data;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Controllers;

public class SanPhamController(AppDbContext db) : Controller
{
    [HttpGet]
    public async Task<IActionResult> CuaHang(int? categoryId, string? search, string sort = "newest", int page = 1, CancellationToken ct = default)
    {
        search = search?.Trim();
        if (!ModelState.IsValid || categoryId <= 0 || page <= 0 || search?.Length > 150 || sort is not ("newest" or "price-asc" or "price-desc")) return BadRequest();
        var model = await StoreCatalog.LoadAsync(db, categoryId, search, sort, page, ct);
        return model == null ? NotFound() : View(model);
    }

    [HttpGet]
    public async Task<IActionResult> ChiTietSanPham([FromRoute] int id, int reviewPage=1, CancellationToken ct=default)
    {
        if (!ModelState.IsValid || id <= 0) return NotFound();
        if(reviewPage<1 || reviewPage>100000) return BadRequest();
        var model = await StoreCatalog.Project(StoreCatalog.Saleable(db).Where(p => p.Id == id), db).FirstOrDefaultAsync(ct);
        if(model==null) return NotFound();
        reviewPage=Math.Min(reviewPage,Math.Max(1,(int)Math.Ceiling(model.ReviewCount/20d)));
        ViewData["ReviewPage"]=reviewPage;
        ViewData["Reviews"]=await db.ProductReviews.AsNoTracking().Include(r=>r.User).Where(r=>r.IsCurrent && !r.IsHidden && r.ProductId==id).OrderByDescending(r=>r.Id).Skip((reviewPage-1)*20).Take(20).ToListAsync(ct);
        return View(model);
    }
}
