namespace GreenShop.Web.Models;

public class StoreNavigationCategoryViewModel
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public int ProductCount { get; set; }
    public string? ImageUrl { get; set; }
}

public class StoreNavigationViewModel
{
    public IReadOnlyList<StoreNavigationCategoryViewModel> Categories { get; set; } = Array.Empty<StoreNavigationCategoryViewModel>();
    public string Controller { get; set; } = string.Empty;
    public int? CategoryId { get; set; }
    public string Search { get; set; } = string.Empty;
}
