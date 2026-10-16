using GreenShop.Web.Models;
using System.Globalization;

namespace GreenShop.Web.Services;

public static class OrderWorkflow
{
    public static readonly IReadOnlyList<OrderStatus> Steps = new[] { OrderStatus.Pending, OrderStatus.Confirmed, OrderStatus.Processing, OrderStatus.Shipping, OrderStatus.Completed };
    public static IReadOnlyList<OrderStatus> States { get; } = Steps.Append(OrderStatus.Cancelled).ToArray();
    public static OrderStatus? Next(OrderStatus status) => status switch
    {
        OrderStatus.Pending => OrderStatus.Confirmed,
        OrderStatus.Confirmed => OrderStatus.Processing,
        OrderStatus.Processing => OrderStatus.Shipping,
        OrderStatus.Shipping => OrderStatus.Completed,
        _ => null
    };
    public static bool CanCancel(OrderStatus status) => status is OrderStatus.Pending or OrderStatus.Confirmed or OrderStatus.Processing;
    public static string Label(OrderStatus status) => status switch
    {
        OrderStatus.Pending => "Chờ xác nhận", OrderStatus.Confirmed => "Đã xác nhận",
        OrderStatus.Processing => "Đang xử lý", OrderStatus.Shipping => "Đang giao",
        OrderStatus.Completed => "Đã giao", OrderStatus.Cancelled => "Đã hủy", _ => "Trạng thái chưa hỗ trợ"
    };
    public static string Tone(OrderStatus status) => status switch
    {
        OrderStatus.Pending => "pending", OrderStatus.Confirmed => "confirmed", OrderStatus.Processing => "processing",
        OrderStatus.Shipping => "shipping", OrderStatus.Completed => "delivered", OrderStatus.Cancelled => "cancelled", _ => "unknown"
    };
    public static string ActionLabel(OrderStatus status) => status switch
    {
        OrderStatus.Confirmed => "Xác nhận đơn", OrderStatus.Processing => "Bắt đầu xử lý",
        OrderStatus.Shipping => "Bắt đầu giao hàng", OrderStatus.Completed => "Xác nhận đã giao", _ => "Cập nhật"
    };
    public static string Code(int id) => $"GS-{id:D6}";
    public static string Money(decimal value) => value.ToString(value == decimal.Truncate(value) ? "N0" : "N2", CultureInfo.GetCultureInfo("vi-VN")) + " đ";
    public static string InventoryLabel(OrderInventoryStatus status) => status switch
    {
        OrderInventoryStatus.Deducted => "Đã trừ khi đặt hàng",
        OrderInventoryStatus.Restored => "Đã hoàn khi hủy",
        _ => "Chưa xác minh trừ kho (đơn cũ)"
    };
}
