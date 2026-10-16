using GreenShop.Web.Data;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.ViewComponents;

public class CartCountViewComponent(AppDbContext db) : ViewComponent
{
    public async Task<IViewComponentResult> InvokeAsync()
    {
        var userId = ShoppingIdentity.UserId(UserClaimsPrincipal);
        if (userId == 0) return Content(string.Empty);
        var count = await db.CartItems.AsNoTracking().Where(i => i.UserId == userId).SumAsync(i => (long?)i.Quantity, HttpContext.RequestAborted) ?? 0;
        return Content($" ({count})");
    }
}
