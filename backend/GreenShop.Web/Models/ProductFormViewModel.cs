using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.AspNetCore.Mvc.ModelBinding.Validation;
using Microsoft.AspNetCore.Mvc.Rendering;

namespace GreenShop.Web.Models;

public class ProductFormViewModel : IValidatableObject
{
    [Required(ErrorMessage = "Vui lòng nhập tên sản phẩm.")]
    [StringLength(150, ErrorMessage = "Tên sản phẩm tối đa 150 ký tự.")]
    [Display(Name = "Tên sản phẩm")]
    public string Name { get; set; } = string.Empty;

    [Required(ErrorMessage = "Vui lòng nhập giá bán.")]
    [Range(typeof(decimal), "0.01", "9999999999.99", ErrorMessage = "Giá bán phải từ 0,01 đến 9.999.999.999,99 VNĐ.")]
    [Display(Name = "Giá bán (VNĐ)")]
    public decimal? Price { get; set; }

    [StringLength(2000, ErrorMessage = "Mô tả tối đa 2000 ký tự.")]
    [Display(Name = "Mô tả")]
    public string? Description { get; set; }

    [Required(ErrorMessage = "Vui lòng nhập số lượng tồn kho.")]
    [Range(0, int.MaxValue, ErrorMessage = "Tồn kho phải là số nguyên không âm.")]
    [Display(Name = "Số lượng tồn kho")]
    public int? StockQuantity { get; set; }

    [Range(0,int.MaxValue)]
    public int? ExpectedStockQuantity { get; set; }

    [Display(Name = "Ảnh sản phẩm")]
    public IFormFile? Image { get; set; }

    [Range(1, int.MaxValue, ErrorMessage = "Danh mục không hợp lệ.")]
    [Display(Name = "Danh mục")]
    public int? CategoryId { get; set; }

    [BindNever, ValidateNever]
    public IReadOnlyList<SelectListItem> Categories { get; set; } = Array.Empty<SelectListItem>();

    [BindNever, ValidateNever]
    public string? ExistingImageUrl { get; set; }

    [BindNever, ValidateNever]
    public int ProductId { get; set; }

    public IEnumerable<ValidationResult> Validate(ValidationContext validationContext)
    {
        if (Price.HasValue && decimal.Round(Price.Value, 2) != Price.Value)
            yield return new ValidationResult("Giá bán tối đa hai chữ số thập phân.", new[] { nameof(Price) });
    }
}
