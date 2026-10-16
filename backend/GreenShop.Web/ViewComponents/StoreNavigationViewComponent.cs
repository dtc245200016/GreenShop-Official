using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.ViewComponents;

public class StoreNavigationViewComponent(AppDbContext db) : ViewComponent
{
    private static readonly object CategoryCacheKey = new();

    public async Task<IViewComponentResult> InvokeAsync(string placement = "Header")
    {
        // Header, discovery and footer share one projection per request, never a stale cross-request cache.
        if (HttpContext.Items[CategoryCacheKey] is not IReadOnlyList<StoreNavigationCategoryViewModel> categories)
        {
            categories = await db.Categories.AsNoTracking().Where(c => c.IsActive).OrderBy(c => c.Name)
                .Select(c => new StoreNavigationCategoryViewModel
                {
                    Id = c.Id, Name = c.Name, ProductCount = c.Products.Count,
                    ImageUrl = c.Products.OrderByDescending(p => p.Id).Select(p => p.ImageUrl).FirstOrDefault()
                }).ToListAsync(HttpContext.RequestAborted);
            HttpContext.Items[CategoryCacheKey] = categories;
        }
        return View(placement is "Discovery" or "Footer" ? placement : "Header", new StoreNavigationViewModel
        {
            Categories = categories,
            Controller = ViewContext.RouteData.Values["controller"]?.ToString() ?? string.Empty,
            CategoryId = int.TryParse(HttpContext.Request.Query["categoryId"], out var id) ? id : null,
            Search = HttpContext.Request.Query["search"].ToString()
        });
    }
}
