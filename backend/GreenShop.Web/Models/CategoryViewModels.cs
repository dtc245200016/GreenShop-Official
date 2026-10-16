using System.ComponentModel.DataAnnotations;

namespace GreenShop.Web.Models;

public class CategoryFormViewModel
{
    [Required(ErrorMessage = "Vui lòng nhập tên danh mục.")]
    [StringLength(100, ErrorMessage = "Tên danh mục tối đa 100 ký tự.")]
    [Display(Name = "Tên danh mục")]
    public string Name { get; set; } = string.Empty;

    [StringLength(500, ErrorMessage = "Mô tả tối đa 500 ký tự.")]
    [Display(Name = "Mô tả")]
    public string? Description { get; set; }

    [Display(Name = "Đang hoạt động")]
    public bool IsActive { get; set; } = true;
}

public class CategoryItemViewModel
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public bool IsActive { get; set; }
    public int ProductCount { get; set; }
}

public class CategoryListViewModel
{
    public IReadOnlyList<CategoryItemViewModel> Categories { get; set; } = Array.Empty<CategoryItemViewModel>();
    public string? Search { get; set; }
    public bool? IsActive { get; set; }
    public int TotalCount { get; set; }
    public int ActiveCount { get; set; }
    public int InactiveCount => TotalCount - ActiveCount;
}
