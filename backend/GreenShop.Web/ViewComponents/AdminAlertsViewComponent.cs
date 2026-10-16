using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc;

namespace GreenShop.Web.ViewComponents;

public class AdminAlertsViewComponent(AppDbContext db) : ViewComponent
{
    public async Task<IViewComponentResult> InvokeAsync(string kind="all")
    {
        if(!User.IsInRole("Admin")) return Content("");
        const string key="GreenShop.AdminAlerts";
        var counts=HttpContext.Items[key] as ShopAlertCounts;
        if(counts==null) {counts=await ShopCommunication.AlertsAsync(db,ShoppingIdentity.UserId(HttpContext.User),HttpContext.RequestAborted);HttpContext.Items[key]=counts;}
        ViewData["Kind"]=kind;return View(counts);
    }
}
