using GreenShop.Web.Services;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.EntityFrameworkCore;
using MySqlConnector;

namespace GreenShop.Web.Areas.Admin.Controllers;

[Area("Admin")]
[Authorize(Roles = "Admin")]
public class DanhMucController : Controller
{
    private readonly AppDbContext _db;
    private readonly ILogger<DanhMucController> _logger;

    public DanhMucController(AppDbContext db, ILogger<DanhMucController> logger)
    {
        _db = db;
        _logger = logger;
    }

    [HttpGet]
    public async Task<IActionResult> QuanLyDanhMuc(string? search, bool? isActive, CancellationToken cancellationToken)
    {
        if (!ModelState.IsValid) return BadRequest();
        search = search?.Trim();
        if (search?.Length > 100) return BadRequest();
        var query = _db.Categories.AsNoTracking();
        var totals = await query.GroupBy(c => 1)
            .Select(g => new { Total = g.Count(), Active = g.Count(c => c.IsActive) })
            .FirstOrDefaultAsync(cancellationToken);
        if (!string.IsNullOrEmpty(search)) query = query.Where(c => c.Name.Contains(search));
        if (isActive.HasValue) query = query.Where(c => c.IsActive == isActive.Value);
        return View(new CategoryListViewModel
        {
            Search = search,
            IsActive = isActive,
            TotalCount = totals?.Total ?? 0,
            ActiveCount = totals?.Active ?? 0,
            Categories = await query.OrderBy(c => c.Name).Select(c => new CategoryItemViewModel
            {
                Id = c.Id, Name = c.Name, Description = c.Description,
                IsActive = c.IsActive, ProductCount = c.Products.Count
            }).ToListAsync(cancellationToken)
        });
    }

    [HttpGet]
    public IActionResult ThemDanhMuc() => View(new CategoryFormViewModel());

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> ThemDanhMuc(CategoryFormViewModel model, CancellationToken cancellationToken)
    {
        await ValidateFormAsync(model, null, cancellationToken);
        if (!ModelState.IsValid) return View(model);
        _db.Categories.Add(new Category
        {
            Name = model.Name.Trim(), Description = model.Description?.Trim() ?? string.Empty, IsActive = model.IsActive
        });
        try
        {
            await _db.SaveChangesAsync(cancellationToken);
            Observability.BusinessCreated(_logger, HttpContext, "category.created");
            TempData["SuccessMessage"] = "Đã thêm danh mục.";
            return RedirectToAction(nameof(QuanLyDanhMuc));
        }
        catch (DbUpdateException exception)
        {
            AddSaveError(exception);
            return View(model);
        }
    }

    [HttpGet]
    public async Task<IActionResult> SuaDanhMuc([FromRoute] int id, CancellationToken cancellationToken)
    {
        var category = await _db.Categories.AsNoTracking().FirstOrDefaultAsync(c => c.Id == id, cancellationToken);
        return category == null ? NotFound() : View(new CategoryFormViewModel
        {
            Name = category.Name, Description = category.Description, IsActive = category.IsActive
        });
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> SuaDanhMuc([FromRoute] int id, CategoryFormViewModel model, CancellationToken cancellationToken)
    {
        var category = await _db.Categories.FirstOrDefaultAsync(c => c.Id == id, cancellationToken);
        if (category == null) return NotFound();
        await ValidateFormAsync(model, id, cancellationToken);
        if (!ModelState.IsValid) return View(model);
        category.Name = model.Name.Trim();
        category.Description = model.Description?.Trim() ?? string.Empty;
        category.IsActive = model.IsActive;
        try
        {
            await _db.SaveChangesAsync(cancellationToken);
            TempData["SuccessMessage"] = "Đã cập nhật danh mục.";
            return RedirectToAction(nameof(QuanLyDanhMuc));
        }
        catch (DbUpdateConcurrencyException)
        {
            return NotFound();
        }
        catch (DbUpdateException exception)
        {
            AddSaveError(exception);
            return View(model);
        }
    }

    [HttpGet]
    public async Task<IActionResult> ChiTietDanhMuc([FromRoute] int id, CancellationToken cancellationToken)
    {
        var category = await GetItemAsync(id, cancellationToken);
        return category == null ? NotFound() : View(category);
    }

    [HttpGet]
    public async Task<IActionResult> XoaDanhMuc([FromRoute] int id, CancellationToken cancellationToken)
    {
        var category = await GetItemAsync(id, cancellationToken);
        return category == null ? NotFound() : View(category);
    }

    [HttpPost, ActionName("XoaDanhMuc"), ValidateAntiForgeryToken]
    public async Task<IActionResult> XacNhanXoaDanhMuc([FromRoute] int id, CancellationToken cancellationToken)
    {
        var category = await _db.Categories.FirstOrDefaultAsync(c => c.Id == id, cancellationToken);
        if (category == null) return NotFound();
        if (await _db.Products.AnyAsync(p => p.CategoryId == id, cancellationToken))
            return await DeleteBlockedAsync(id, cancellationToken);
        _db.Categories.Remove(category);
        try
        {
            await _db.SaveChangesAsync(cancellationToken);
            TempData["SuccessMessage"] = "Đã xóa danh mục.";
            return RedirectToAction(nameof(QuanLyDanhMuc));
        }
        catch (DbUpdateConcurrencyException)
        {
            return NotFound();
        }
        catch (DbUpdateException exception) when (exception.InnerException is MySqlException { Number: 1451 })
        {
            // FK RESTRICT protects a product linked after the dependency check.
            return await DeleteBlockedAsync(id, cancellationToken);
        }
        catch (DbUpdateException exception)
        {
            _logger.LogError(exception, "Không thể xóa danh mục {CategoryId}.", id);
            ModelState.AddModelError(string.Empty, "Không thể xóa danh mục. Vui lòng thử lại sau.");
            var item = await GetItemAsync(id, cancellationToken);
            return item == null ? NotFound() : View("XoaDanhMuc", item);
        }
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> ThayDoiTrangThaiDanhMuc([FromRoute] int id, [FromForm, BindRequired] bool isActive, CancellationToken cancellationToken)
    {
        if (!ModelState.IsValid) return BadRequest();
        var category = await _db.Categories.FirstOrDefaultAsync(c => c.Id == id, cancellationToken);
        if (category == null) return NotFound();
        category.IsActive = isActive;
        try
        {
            await _db.SaveChangesAsync(cancellationToken);
            TempData["SuccessMessage"] = isActive ? "Danh mục đã được bật hoạt động." : "Danh mục đã ngừng hoạt động. Sản phẩm hiện có vẫn giữ danh mục.";
        }
        catch (DbUpdateConcurrencyException)
        {
            return NotFound();
        }
        catch (DbUpdateException exception)
        {
            _logger.LogError(exception, "Không thể đổi trạng thái danh mục {CategoryId}.", id);
            TempData["ErrorMessage"] = "Không thể đổi trạng thái. Vui lòng thử lại sau.";
        }
        return RedirectToAction(nameof(QuanLyDanhMuc));
    }

    private Task<CategoryItemViewModel?> GetItemAsync(int id, CancellationToken cancellationToken) =>
        _db.Categories.AsNoTracking().Where(c => c.Id == id).Select(c => new CategoryItemViewModel
        {
            Id = c.Id, Name = c.Name, Description = c.Description,
            IsActive = c.IsActive, ProductCount = c.Products.Count
        }).FirstOrDefaultAsync(cancellationToken);

    private async Task ValidateFormAsync(CategoryFormViewModel model, int? id, CancellationToken cancellationToken)
    {
        if (ModelState.TryGetValue(nameof(model.IsActive), out var status) && status.Errors.Count > 0)
        {
            // Preserve the validation error while giving the checkbox a renderable boolean value.
            status.Errors.Clear();
            ModelState.AddModelError(nameof(model.IsActive), "Trạng thái danh mục không hợp lệ. Vui lòng chọn lại.");
            var value = model.IsActive ? "true" : "false";
            ModelState.SetModelValue(nameof(model.IsActive), value, value);
        }
        if (string.IsNullOrWhiteSpace(model.Name) || model.Name.Length > 100) return;
        var name = model.Name.Trim();
        if (await _db.Categories.AnyAsync(c => c.Name == name && (!id.HasValue || c.Id != id.Value), cancellationToken))
            ModelState.AddModelError(nameof(model.Name), "Tên danh mục đã tồn tại. Vui lòng chọn tên khác.");
    }

    private void AddSaveError(DbUpdateException exception)
    {
        if (exception.InnerException is MySqlException { Number: 1062 })
            ModelState.AddModelError(nameof(CategoryFormViewModel.Name), "Tên danh mục đã tồn tại. Vui lòng chọn tên khác.");
        else
        {
            _logger.LogError(exception, "Không thể lưu danh mục.");
            ModelState.AddModelError(string.Empty, "Không thể lưu danh mục. Vui lòng thử lại sau.");
        }
    }

    private async Task<IActionResult> DeleteBlockedAsync(int id, CancellationToken cancellationToken)
    {
        ModelState.AddModelError(string.Empty, "Không thể xóa danh mục đang có sản phẩm. Hãy chuyển sản phẩm sang danh mục khác trước.");
        var item = await GetItemAsync(id, cancellationToken);
        return item == null ? NotFound() : View("XoaDanhMuc", item);
    }
}
