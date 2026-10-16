using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.AspNetCore.Mvc.ModelBinding.Validation;

namespace GreenShop.Web.Models;

public static class StoreDisplay
{
    public static string Money(decimal value) => GreenShop.Web.Services.OrderWorkflow.Money(value);
    public static string Image(string? value)
    {
        if (value?.StartsWith("/uploads/products/", StringComparison.Ordinal) == true && !value.Contains("..") && !value.Contains('\\')) return value;
        if (Uri.TryCreate(value, UriKind.Absolute, out var uri) && uri.Scheme == Uri.UriSchemeHttps) return uri.AbsoluteUri;
        return "/images/product-placeholder.svg";
    }
}

public class StoreProductViewModel
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public decimal Price { get; set; }
    public string ImageUrl { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public int StockQuantity { get; set; }
    public int? CategoryId { get; set; }
    public string CategoryName { get; set; } = "Chưa phân loại";
    public long SoldCount { get; set; }
    public int ReviewCount { get; set; }
    public double? AverageStars { get; set; }
}

public class StoreCategoryViewModel
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;
    public int ProductCount { get; set; }
}

public class StoreCatalogViewModel
{
    public IReadOnlyList<StoreProductViewModel> HeroProducts { get; set; } = Array.Empty<StoreProductViewModel>();
    public IReadOnlyList<StoreProductViewModel> Products { get; set; } = Array.Empty<StoreProductViewModel>();
    public IReadOnlyList<StoreCategoryViewModel> Categories { get; set; } = Array.Empty<StoreCategoryViewModel>();
    public int? CategoryId { get; set; }
    public string? CategoryName { get; set; }
    public string? Search { get; set; }
    public string Sort { get; set; } = "newest";
    public int Page { get; set; } = 1;
    public int TotalCount { get; set; }
    public int PageSize { get; set; } = 12;
    public int TotalPages => Math.Max(1, (int)Math.Ceiling((double)TotalCount / PageSize));
}

public class QuantityViewModel
{
    [BindRequired, Range(1, 1_000_000, ErrorMessage = "Số lượng phải từ 1 đến 1.000.000.")]
    public int Quantity { get; set; } = 1;
}

public class CartRowViewModel
{
    public int Id { get; set; }
    public StoreProductViewModel Product { get; set; } = new();
    public int Quantity { get; set; }
    public bool Available { get; set; }
    public decimal Total => Product.Price * Quantity;
    public bool CanBuy => Available && Quantity > 0 && Quantity <= Product.StockQuantity;
}

public class CartViewModel
{
    public IReadOnlyList<CartRowViewModel> Items { get; set; } = Array.Empty<CartRowViewModel>();
    public decimal Total => Items.Where(i => i.CanBuy).Sum(i => i.Total);
}

public class CheckoutViewModel : QuantityViewModel
{
    [Required(ErrorMessage = "Vui lòng nhập tên người nhận."), StringLength(100), Display(Name = "Người nhận")]
    public string RecipientName { get; set; } = string.Empty;
    [Required(ErrorMessage = "Vui lòng nhập số điện thoại."), RegularExpression(@"\+?[0-9][0-9\s().-]{7,19}", ErrorMessage = "Số điện thoại không hợp lệ."), Display(Name = "Số điện thoại")]
    public string Phone { get; set; } = string.Empty;
    [Required(ErrorMessage = "Vui lòng nhập địa chỉ giao hàng."), StringLength(500, MinimumLength = 10, ErrorMessage = "Địa chỉ cần từ 10 đến 500 ký tự."), Display(Name = "Địa chỉ giao hàng")]
    public string Address { get; set; } = string.Empty;
    [Required, RegularExpression("^[a-f0-9]{32}$")]
    public string ConfirmationToken { get; set; } = string.Empty;
    [Required, Range(typeof(decimal), "0.01", "9999999999.99")]
    public decimal? QuotedPrice { get; set; }
    [BindRequired,Range(0,long.MaxValue-1)] public long PolicyVersion { get; set; }
    [Required,RegularExpression("^(COD|VIETQR)$")] public string PaymentMethod { get; set; } = PaymentMethods.Cod;
    public string? CartQuote { get; set; }
    [BindNever, ValidateNever]
    public StoreProductViewModel Product { get; set; } = new();
    [BindNever,ValidateNever] public IReadOnlyList<CheckoutLine> Lines { get; set; } = Array.Empty<CheckoutLine>();
    [BindNever,ValidateNever] public PaymentShippingSettings Policy { get; set; } = new();
    [BindNever] public bool FromCart { get; set; }
    public decimal Subtotal => FromCart ? Lines.Sum(i=>i.Price*i.Quantity) : Product.Price*Quantity;
    public decimal ShippingFee => Services.ShippingFees.Calculate(Subtotal,Policy);
    public decimal Total => Subtotal+ShippingFee;
}
