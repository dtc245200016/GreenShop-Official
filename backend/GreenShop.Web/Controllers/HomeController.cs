using System.Diagnostics;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc;

namespace GreenShop.Web.Controllers;

public class HomeController(AppDbContext db) : Controller
{
    [HttpGet]
    public async Task<IActionResult> Index(CancellationToken ct)
    {
        var model=(await StoreCatalog.LoadAsync(db,null,null,"newest",1,ct))!;
        model.HeroProducts=await StoreCatalog.HeroAsync(db,ct);
        return View(model);
    }

    [ResponseCache(Duration = 0, Location = ResponseCacheLocation.None, NoStore = true)]
    public IActionResult Error() => View(new ErrorViewModel { RequestId = Activity.Current?.Id ?? HttpContext.TraceIdentifier });

    [ResponseCache(Duration = 0, Location = ResponseCacheLocation.None, NoStore = true)]
    public IActionResult ThongBaoHttp(int statusCode = 404)
    {
        Response.StatusCode = statusCode is 400 or 404 or 405 ? statusCode : 404;
        return View(Response.StatusCode);
    }
}
