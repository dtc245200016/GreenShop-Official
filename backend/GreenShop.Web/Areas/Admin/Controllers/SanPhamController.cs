using System.Data.Common;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Rendering;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Areas.Admin.Controllers;

[Area("Admin")]
[Authorize(Roles = "Admin")]
[RequestSizeLimit(6 * 1024 * 1024)]
[RequestFormLimits(MultipartBodyLengthLimit = 6 * 1024 * 1024)]
public class SanPhamController : Controller
{
    private readonly AppDbContext _db;
    private readonly ProductImageStorage _images;
    private readonly ILogger<SanPhamController> _logger;
    private readonly IConfiguration _configuration;

    public SanPhamController(AppDbContext db, IWebHostEnvironment environment, ILogger<SanPhamController> logger, IConfiguration configuration)
    {
        _db = db;
        _logger = logger;
        _configuration = configuration;
        _images = new ProductImageStorage(environment, logger);
    }

    [HttpGet]
    public async Task<IActionResult> QuanLySanPham(CancellationToken cancellationToken)
    {
        return View(await _db.Products.AsNoTracking().Include(p => p.Category).OrderByDescending(p => p.Id).ToListAsync(cancellationToken));
    }

    [HttpGet, ResponseCache(NoStore=true,Location=ResponseCacheLocation.None)]
    public Task<IActionResult> XuatExcelSanPham(CancellationToken ct) => ExcelDownload.RunAsync(async token =>
    {
        var limit=ExcelExportPolicy.MaxRows(_configuration);
        // Product administration currently displays all products, ordered by ID; no filters/paging exist.
        var rows=await _db.Products.AsNoTracking().OrderByDescending(p=>p.Id)
            .Select(p=>new ProductExportRow(p.Id,p.Name,p.Category==null ? "Chưa phân loại" : p.Category.Name,p.Price,p.StockQuantity))
            .Take(limit+1).ToListAsync(token);
        ExcelExportPolicy.CheckCount(rows.Count,limit);
        return ExcelExportService.Products(rows,ExcelExportPolicy.LowStockThreshold(_configuration),token);
    },"SanPhamTonKho",_logger,ct);

    [HttpGet]
    public async Task<IActionResult> ChiTietSanPham([FromRoute] int id, CancellationToken cancellationToken)
    {
        var product = await _db.Products.AsNoTracking().Include(p => p.Category).FirstOrDefaultAsync(p => p.Id == id, cancellationToken);
        return product == null ? NotFound() : View(product);
    }

    [HttpGet]
    public async Task<IActionResult> ThemSanPham(CancellationToken cancellationToken)
    {
        var model = new ProductFormViewModel { StockQuantity = 0 };
        await LoadCategoriesAsync(model, null, cancellationToken);
        return View(model);
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> ThemSanPham(ProductFormViewModel model, CancellationToken cancellationToken)
    {
        await ValidateCategoryAsync(model, null, cancellationToken);
        await ValidateImageAsync(model, required: true, cancellationToken);
        if (!ModelState.IsValid) return View(model);

        string? imageUrl = null;
        try
        {
            imageUrl = await _images.SaveAsync(model.Image!, cancellationToken);
            var product = new Product { ImageUrl = imageUrl };
            ApplyForm(product, model);
            _db.Products.Add(product);
            await _db.SaveChangesAsync(cancellationToken);
            Observability.BusinessCreated(_logger, HttpContext, "product.created");
            TempData["SuccessMessage"] = "Đã thêm sản phẩm.";
            return RedirectToAction(nameof(QuanLySanPham));
        }
        catch (Exception exception) when (exception is DbUpdateException or IOException or UnauthorizedAccessException)
        {
            if (imageUrl != null && !_images.Delete(imageUrl))
                ModelState.AddModelError(string.Empty, "Một ảnh mới chưa được dọn; vui lòng liên hệ quản trị hệ thống.");
            _logger.LogError(exception, "Không thể thêm sản phẩm.");
            ModelState.AddModelError(string.Empty, "Không thể lưu sản phẩm. Vui lòng thử lại sau.");
            return View(model);
        }
        catch (OperationCanceledException)
        {
            if (imageUrl != null) _images.Delete(imageUrl);
            throw;
        }
    }

    [HttpGet]
    public async Task<IActionResult> SuaSanPham([FromRoute] int id, CancellationToken cancellationToken)
    {
        var product = await _db.Products.AsNoTracking().FirstOrDefaultAsync(p => p.Id == id, cancellationToken);
        if (product == null) return NotFound();
        var model = new ProductFormViewModel
        {
            Name = product.Name, Price = product.Price, Description = product.Description,
            StockQuantity = product.StockQuantity, ExpectedStockQuantity=product.StockQuantity, ExistingImageUrl = product.ImageUrl, ProductId = product.Id,
            CategoryId = product.CategoryId
        };
        await LoadCategoriesAsync(model, product.CategoryId, cancellationToken);
        return View(model);
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> SuaSanPham([FromRoute] int id, ProductFormViewModel model, CancellationToken cancellationToken)
    {
        var product = await _db.Products.AsNoTracking().FirstOrDefaultAsync(p => p.Id == id, cancellationToken);
        if (product == null) return NotFound();
        model.ExistingImageUrl = product.ImageUrl;
        model.ProductId = product.Id;
        await ValidateCategoryAsync(model, product.CategoryId, cancellationToken);
        await ValidateImageAsync(model, required: false, cancellationToken);
        if(!model.ExpectedStockQuantity.HasValue)
            ModelState.AddModelError(string.Empty,"Vui lòng tải lại trang sửa sản phẩm để đối chiếu tồn kho trước khi lưu.");
        if (!ModelState.IsValid) return View(model);

        var oldImageUrl = product.ImageUrl;
        var expectedStock=model.ExpectedStockQuantity.GetValueOrDefault();
        string? newImageUrl = null;
        try
        {
            if (model.Image != null)
                newImageUrl = await _images.SaveAsync(model.Image, cancellationToken);
            var changed=await _db.Database.CreateExecutionStrategy().ExecuteAsync(async()=>
            {
                await using var transaction=await _db.Database.BeginTransactionAsync(System.Data.IsolationLevel.ReadCommitted,cancellationToken);
                var actor=await ShoppingIdentity.LockUserAsync(_db,ShoppingIdentity.UserId(User),cancellationToken);
                if(actor==null||!actor.IsActive||actor.Role!=UserRole.Admin||actor.SessionVersion!=UserSession.Version(User))return -1;
                var count=await _db.Products.Where(p=>p.Id==id&&p.StockQuantity==expectedStock)
                    .ExecuteUpdateAsync(s=>s.SetProperty(p=>p.Name,model.Name.Trim()).SetProperty(p=>p.Price,model.Price!.Value)
                        .SetProperty(p=>p.Description,model.Description==null?"":model.Description.Trim()).SetProperty(p=>p.StockQuantity,model.StockQuantity!.Value)
                        .SetProperty(p=>p.CategoryId,model.CategoryId).SetProperty(p=>p.ImageUrl,newImageUrl??oldImageUrl),cancellationToken);
                if(count==1)await transaction.CommitAsync(cancellationToken);
                return count;
            });
            if(changed!=1)
            {
                if(newImageUrl!=null)_images.Delete(newImageUrl);
                if(changed==-1)return Forbid();
                var current=await _db.Products.AsNoTracking().FirstOrDefaultAsync(p=>p.Id==id,cancellationToken);
                if(current==null)return NotFound();
                model.ExistingImageUrl=current.ImageUrl;model.ExpectedStockQuantity=current.StockQuantity;model.StockQuantity=current.StockQuantity;
                ModelState.Remove(nameof(model.ExpectedStockQuantity));ModelState.Remove(nameof(model.StockQuantity));
                ModelState.AddModelError(string.Empty,"Tồn kho đã thay đổi do đặt hàng hoặc cập nhật khác. Số lượng mới đã được tải; vui lòng kiểm tra và xác nhận lại.");
                Response.StatusCode=409;return View(model);
            }
        }
        catch (Exception exception) when (exception is DbUpdateException or IOException or UnauthorizedAccessException)
        {
            if (newImageUrl != null && !_images.Delete(newImageUrl))
                ModelState.AddModelError(string.Empty, "Một ảnh mới chưa được dọn; vui lòng liên hệ quản trị hệ thống.");
            _logger.LogError(exception, "Không thể cập nhật sản phẩm {ProductId}.", id);
            if (exception is DbUpdateConcurrencyException
                && !await _db.Products.AsNoTracking().AnyAsync(p => p.Id == id, cancellationToken))
                return NotFound();
            ModelState.AddModelError(string.Empty, "Không thể cập nhật sản phẩm. Ảnh cũ được giữ nguyên.");
            return View(model);
        }

        catch (OperationCanceledException)
        {
            if (newImageUrl != null) _images.Delete(newImageUrl);
            throw;
        }

        if (newImageUrl != null) await CleanupUnreferencedImageAsync(oldImageUrl);
        TempData["SuccessMessage"] = "Đã cập nhật sản phẩm.";
        return RedirectToAction(nameof(QuanLySanPham));
    }

    [HttpGet]
    public async Task<IActionResult> XoaSanPham([FromRoute] int id, CancellationToken cancellationToken)
    {
        var product = await _db.Products.AsNoTracking().FirstOrDefaultAsync(p => p.Id == id, cancellationToken);
        return product == null ? NotFound() : View(product);
    }

    [HttpPost, ActionName("XoaSanPham"), ValidateAntiForgeryToken]
    public async Task<IActionResult> XacNhanXoaSanPham([FromRoute] int id, CancellationToken cancellationToken)
    {
        var product = await _db.Products.FirstOrDefaultAsync(p => p.Id == id, cancellationToken);
        if (product == null) return NotFound();
        try
        {
            _db.Products.Remove(product);
            await _db.SaveChangesAsync(cancellationToken);
        }
        catch (DbUpdateException exception)
        {
            _logger.LogError(exception, "Không thể xóa sản phẩm {ProductId}.", id);
            if (exception is DbUpdateConcurrencyException
                && !await _db.Products.AsNoTracking().AnyAsync(p => p.Id == id, cancellationToken))
                return NotFound();
            ModelState.AddModelError(string.Empty, "Không thể xóa sản phẩm. Vui lòng thử lại sau.");
            return View("XoaSanPham", product);
        }

        await CleanupUnreferencedImageAsync(product.ImageUrl);
        TempData["SuccessMessage"] = "Đã xóa sản phẩm.";
        return RedirectToAction(nameof(QuanLySanPham));
    }

    private async Task ValidateImageAsync(ProductFormViewModel model, bool required, CancellationToken cancellationToken)
    {
        if (model.Image == null)
        {
            if (required) ModelState.AddModelError(nameof(model.Image), "Vui lòng chọn ảnh sản phẩm.");
            return;
        }
        try
        {
            var error = await _images.ValidateAsync(model.Image, cancellationToken);
            if (error != null) ModelState.AddModelError(nameof(model.Image), error);
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            _logger.LogError(exception, "Không thể đọc ảnh sản phẩm được tải lên.");
            ModelState.AddModelError(nameof(model.Image), "Không thể đọc ảnh. Vui lòng chọn lại file.");
        }
    }

    private static void ApplyForm(Product product, ProductFormViewModel model)
    {
        product.Name = model.Name.Trim();
        product.Price = model.Price!.Value;
        product.Description = model.Description?.Trim() ?? string.Empty;
        product.StockQuantity = model.StockQuantity!.Value;
        product.CategoryId = model.CategoryId;
    }

    private async Task LoadCategoriesAsync(ProductFormViewModel model, int? currentCategoryId, CancellationToken cancellationToken)
    {
        model.Categories = await _db.Categories.AsNoTracking()
            .Where(c => c.IsActive || c.Id == currentCategoryId).OrderBy(c => c.Name)
            .Select(c => new SelectListItem
            {
                Value = c.Id.ToString(), Text = c.Name + (c.IsActive ? "" : " (Ngừng hoạt động — hiện tại)")
            }).ToListAsync(cancellationToken);
    }

    private async Task ValidateCategoryAsync(ProductFormViewModel model, int? currentCategoryId, CancellationToken cancellationToken)
    {
        if (model.CategoryId.HasValue && !await _db.Categories.AsNoTracking()
            .AnyAsync(c => c.Id == model.CategoryId.Value && (c.IsActive || c.Id == currentCategoryId), cancellationToken))
            ModelState.AddModelError(nameof(model.CategoryId), "Danh mục không tồn tại hoặc đã ngừng hoạt động. Vui lòng chọn lại.");
        await LoadCategoriesAsync(model, currentCategoryId, cancellationToken);
    }

    private async Task CleanupUnreferencedImageAsync(string imageUrl)
    {
        try
        {
            if (!await _db.Products.AsNoTracking().AnyAsync(p => p.ImageUrl == imageUrl)
                && !await _db.OrderItems.AsNoTracking().AnyAsync(i=>i.ImageUrl==imageUrl)
                && !_images.Delete(imageUrl))
                TempData["WarningMessage"] = "Dữ liệu đã được lưu, nhưng một ảnh cũ chưa được dọn. Vui lòng liên hệ quản trị hệ thống.";
        }
        catch (DbException exception)
        {
            _logger.LogWarning(exception, "Chưa thể kiểm tra tham chiếu để dọn ảnh sản phẩm.");
            TempData["WarningMessage"] = "Dữ liệu đã được lưu, nhưng chưa thể dọn ảnh cũ. Vui lòng liên hệ quản trị hệ thống.";
        }
    }
}
