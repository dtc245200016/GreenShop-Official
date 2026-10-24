using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.AspNetCore.Mvc.ModelBinding.Validation;

namespace GreenShop.Web.Models;

public class PaymentShippingSettings
{
    public int Id { get; set; } = 1;
    public string BankBin { get; set; } = "";
    public string BankName { get; set; } = "";
    public string AccountNumber { get; set; } = "";
    public string AccountHolderName { get; set; } = "";
    public bool VietQrEnabled { get; set; }
    public decimal FlatShippingFee { get; set; } = 30000;
    public decimal FreeShippingThreshold { get; set; } = 300000;
    public long Version { get; set; }
    public DateTime? UpdatedAt { get; set; }
}

public class BankSettingsForm
{
    [BindRequired,Range(0,long.MaxValue-1)] public long ExpectedVersion { get; set; }
    [Required,RegularExpression("^[0-9]{6}$")] public string BankBin { get; set; } = "";
    [Required,StringLength(19),RegularExpression("^[A-Za-z0-9]{1,19}$",ErrorMessage="Số tài khoản cần 1–19 ký tự chữ hoặc số, không có khoảng trắng.")]
    public string AccountNumber { get; set; } = "";
    [Required,StringLength(100)] public string AccountHolderName { get; set; } = "";
    public bool VietQrEnabled { get; set; }
    public bool BankDetailsChecked { get; set; }
}
public class ShippingSettingsForm
{
    [BindRequired,Range(0,long.MaxValue-1)] public long ExpectedVersion { get; set; }
    [BindRequired,Range(typeof(decimal),"0","1000000")] public decimal FlatShippingFee { get; set; }
    [BindRequired,Range(typeof(decimal),"0","1000000000")] public decimal FreeShippingThreshold { get; set; }
}
public class PaymentShippingSettingsViewModel
{
    public PaymentShippingSettings Settings { get; set; } = new();
    public BankSettingsForm Bank { get; set; } = new();
    public ShippingSettingsForm Shipping { get; set; } = new();
    public int PendingEarlierBankOrders { get; set; }
}
public record CheckoutLine(int ProductId,string Name,string ImageUrl,decimal Price,int Quantity,int StockQuantity);
public record CheckoutCartQuote(int UserId, IReadOnlyList<CheckoutLine> Items);
public record CheckoutResult(int StatusCode,int OrderId,string Message,bool Created=false);

public static class PaymentMethods
{
    public const string Cod="COD";
    public const string VietQr="VIETQR";
    public static bool Valid(string? method) => method is Cod or VietQr;
    public static string Label(string method) => method switch {Cod=>"Thanh toán khi nhận hàng (COD)",VietQr=>"Chuyển khoản VietQR",_=>method};
    public static string Status(Order order) => order.IsPaid ? "Đã thanh toán" : order.PaymentMethod==VietQr && order.CustomerTransferNotifiedAt.HasValue ? "Chờ kiểm tra chuyển khoản" : "Chưa thanh toán";
    public static string Status(bool paid,string method,DateTime? notified) => paid ? "Đã thanh toán" : method==VietQr && notified.HasValue ? "Chờ kiểm tra chuyển khoản" : "Chưa thanh toán";
    public static bool NeedsTransfer(Order order) => order.PaymentMethod==VietQr && !order.IsPaid && order.Status!=OrderStatus.Cancelled;
    public static bool ValidMoney(Order order)
    {
        if(order.Items.Count==0 || order.Items.Any(i=>i.Quantity<=0 || i.UnitPrice<=0)) return false;
        var items=order.Items.Sum(i=>i.UnitPrice*i.Quantity);
        if(!order.Subtotal.HasValue && !order.ShippingFee.HasValue) return items==order.Total;
        return order.Subtotal==items && order.ShippingFee>=0 && order.Subtotal+order.ShippingFee==order.Total;
    }
}
