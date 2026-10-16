using System.Data.Common;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Areas.Admin.Controllers;

[Area("Admin"), Authorize(Roles = "Admin")]
public class DonHangController(AppDbContext db, ILogger<DonHangController> logger, IConfiguration configuration) : Controller
{
    [HttpGet]
    public async Task<IActionResult> QuanLyDonHang(AdminOrderFilter filter, CancellationToken ct)
    {
        filter.Search = filter.Search?.Trim();
        if (!ModelState.IsValid || !AdminOrderQueries.Valid(filter)) return BadRequest();
        var counts = await db.Orders.AsNoTracking().GroupBy(o => o.Status).Select(g => new { Status = g.Key, Count = g.Count() }).ToDictionaryAsync(g => g.Status, g => g.Count, ct);
        var query = AdminOrderQueries.Apply(db.Orders.AsNoTracking(),filter);
        var total = await query.CountAsync(ct);
        filter.Page = Math.Min(filter.Page, Math.Max(1, (int)Math.Ceiling(total / (double)filter.PageSize)));
        var rows = await query.Skip((filter.Page - 1) * filter.PageSize).Take(filter.PageSize).Select(o => new AdminOrderRow
        {
            Id = o.Id, CustomerName = o.User.FullName, RecipientName = o.RecipientName, CreatedAt = o.CreatedAt,
            Total = o.Total, Quantity = o.Items.Sum(i => (long)i.Quantity), Status = o.Status, IsPaid = o.IsPaid, PaymentMethod = o.PaymentMethod, CustomerTransferNotifiedAt=o.CustomerTransferNotifiedAt
        }).ToListAsync(ct);
        return View(new AdminOrderListViewModel { Filter = filter, Counts = counts, MatchingCount = total, Orders = rows });
    }

    [HttpGet, ResponseCache(NoStore=true,Location=ResponseCacheLocation.None)]
    public Task<IActionResult> XuatExcelDonHang(AdminOrderFilter filter, CancellationToken ct)
    {
        filter.Search=filter.Search?.Trim();
        if(!ModelState.IsValid || !AdminOrderQueries.Valid(filter))
            return Task.FromResult<IActionResult>(ExcelDownload.Error(400,"Bộ lọc không hợp lệ. Kiểm tra khoảng ngày, trạng thái và thứ tự sắp xếp."));
        return ExcelDownload.RunAsync(async token =>
        {
            var limit=ExcelExportPolicy.MaxRows(configuration);
            var rows=await AdminOrderQueries.Apply(db.Orders.AsNoTracking(),filter).Select(OrderExportRow.Projection).Take(limit+1).ToListAsync(token);
            ExcelExportPolicy.CheckCount(rows.Count,limit);
            return ExcelExportService.Orders(rows,filter,token);
        },"DonHang",logger,ct);
    }

    [HttpGet]
    public async Task<IActionResult> ChiTietDonHang([FromRoute] int id, CancellationToken ct) => await DetailAsync(id, false, ct);

    [HttpGet]
    public async Task<IActionResult> InDonHang([FromRoute] int id, CancellationToken ct) => await DetailAsync(id, true, ct);

    [HttpPost, ValidateAntiForgeryToken]
    public Task<IActionResult> XacNhanDonHang([FromRoute] int id, AdminOrderCommand model, CancellationToken ct) =>
        MutateAsync(id, model, AdminOrderOperation.Transition, OrderStatus.Confirmed, ct);

    [HttpPost, ValidateAntiForgeryToken]
    public Task<IActionResult> CapNhatTrangThaiDonHang([FromRoute] int id, AdminOrderTransition model, CancellationToken ct) =>
        MutateAsync(id, model, AdminOrderOperation.Transition, model.TargetStatus, ct);

    [HttpPost, ValidateAntiForgeryToken]
    public Task<IActionResult> HuyDonHang([FromRoute] int id, AdminOrderCommand model, CancellationToken ct) =>
        MutateAsync(id, model, AdminOrderOperation.Cancel, null, ct);

    [HttpPost, ValidateAntiForgeryToken]
    public Task<IActionResult> CapNhatGhiChuDonHang([FromRoute] int id, AdminOrderCommand model, CancellationToken ct) =>
        MutateAsync(id, model, AdminOrderOperation.Note, null, ct);

    [HttpPost, ValidateAntiForgeryToken]
    public Task<IActionResult> XacNhanThuCod([FromRoute] int id, AdminOrderCommand model, CancellationToken ct) =>
        MutateAsync(id, model, AdminOrderOperation.CollectCod, null, ct);

    [HttpPost,ValidateAntiForgeryToken]
    public Task<IActionResult> XacNhanDaNhanTien([FromRoute] int id,AdminOrderCommand model,CancellationToken ct) =>
        MutateAsync(id,model,AdminOrderOperation.CollectBankTransfer,null,ct);

    [HttpPost, ValidateAntiForgeryToken]
    public Task<IActionResult> XacNhanDaTruKho([FromRoute] int id, AdminOrderCommand model, CancellationToken ct) =>
        MutateAsync(id, model, AdminOrderOperation.VerifyInventory, null, ct);

    private async Task<IActionResult> DetailAsync(int id, bool print, CancellationToken ct)
    {
        if (id <= 0) return NotFound();
        var order = await db.Orders.AsNoTracking().Include(o => o.User).Include(o => o.Items).Include(o => o.History).AsSplitQuery()
            .FirstOrDefaultAsync(o => o.Id == id, ct);
        return order == null ? NotFound() : View("ChiTietDonHang", new AdminOrderDetailViewModel { Order = order, Print = print });
    }

    private async Task<IActionResult> MutateAsync(int id, AdminOrderCommand model, AdminOrderOperation operation, OrderStatus? target, CancellationToken ct)
    {
        if (!ModelState.IsValid || id <= 0 || target.HasValue && !Enum.IsDefined(target.Value))
        {
            ModelState.AddModelError(string.Empty, "Thông tin thao tác không hợp lệ. Vui lòng kiểm tra số phiên bản, trạng thái và ghi chú (tối đa 1.000 ký tự).");
            Response.StatusCode = 400;
            return await DetailAsync(id, false, ct);
        }
        OrderMutationResult result;
        try { result = await new AdminOrderService(db).ExecuteAsync(id, ShoppingIdentity.UserId(User), model, operation, target, ct, UserSession.Version(User)); }
        catch (Exception ex) when (ex is DbException or DbUpdateException)
        {
            logger.LogError(ex, "Không thể cập nhật đơn hàng {OrderId}.", id);
            result = new OrderMutationResult(503, "Chưa thể lưu thay đổi. Hãy tải lại đơn để kiểm tra trước khi thử lại.");
        }
        if (result.StatusCode == 404) return NotFound();
        if (result.StatusCode == 403) return Forbid();
        if (result.StatusCode == 200)
        {
            TempData["SuccessMessage"] = result.Message;
            return RedirectToAction(nameof(ChiTietDonHang), new { id });
        }
        Response.StatusCode = result.StatusCode;
        ModelState.AddModelError(string.Empty, result.Message);
        if (operation == AdminOrderOperation.Note) ViewData["SubmittedNote"] = model.Note ?? string.Empty;
        return await DetailAsync(id, false, ct);
    }
}
