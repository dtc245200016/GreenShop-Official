using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using System.Data.Common;
using GreenShop.Web.Services;
using GreenShop.Web.Data;
using GreenShop.Web.Models;

namespace GreenShop.Web.Areas.Admin.Controllers
{
    [Area("Admin")]
    [Authorize(Roles = "Admin")]
    public class AdminController(AppDbContext db, IConfiguration configuration, ILogger<AdminController> logger) : Controller
    {
        [HttpGet]
        public IActionResult Index(string? range) => RedirectToAction(nameof(TongQuan),new {range});

        [HttpGet]
        public async Task<IActionResult> TongQuan(string? range, CancellationToken ct)
        {
            var period=DashboardPeriod.Create(range,DateTime.UtcNow);
            var threshold=ExcelExportPolicy.LowStockThreshold(configuration);
            try { return View(await new DashboardStatistics(db).LoadAsync(period,threshold,ct)); }
            catch (Exception ex) when (ex is DbException or Microsoft.EntityFrameworkCore.Storage.RetryLimitExceededException)
            {
                logger.LogWarning("Không thể đọc số liệu tổng quan từ database.");
                Response.StatusCode=503;
                return View(new AdminDashboardViewModel {Period=period,Unavailable=true});
            }
        }

        [HttpGet, ResponseCache(NoStore=true,Location=ResponseCacheLocation.None)]
        public Task<IActionResult> XuatBaoCaoDoanhThu(string? range,CancellationToken ct)
        {
            if(!ModelState.IsValid || range is not (null or "7d" or "30d" or "month" or "year"))
                return Task.FromResult<IActionResult>(ExcelDownload.Error(400,"Khoảng thời gian không hợp lệ."));
            return ExcelDownload.RunAsync(async token =>
            {
                var report=await new DashboardStatistics(db).LoadReportAsync(DashboardPeriod.Create(range,DateTime.UtcNow),
                    ExcelExportPolicy.LowStockThreshold(configuration),ExcelExportPolicy.MaxRows(configuration),token);
                return ExcelExportService.Dashboard(report,token);
            },"BaoCaoGiaTriDonDaGiao",logger,ct);
        }
    }
}
