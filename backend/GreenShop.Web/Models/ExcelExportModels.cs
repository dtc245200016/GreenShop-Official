using System.Linq.Expressions;

namespace GreenShop.Web.Models;

public class OrderExportRow
{
    public int Id { get; set; }
    public DateTime CreatedAt { get; set; }
    public string CustomerName { get; set; } = "";
    public string RecipientName { get; set; } = "";
    public string Phone { get; set; } = "";
    public string Address { get; set; } = "";
    public int ItemKinds { get; set; }
    public long Quantity { get; set; }
    public decimal Total { get; set; }
    public string PaymentMethod { get; set; } = "";
    public bool IsPaid { get; set; }
    public OrderStatus Status { get; set; }
    public decimal? Subtotal { get; set; }
    public decimal? ShippingFee { get; set; }
    public DateTime? CustomerTransferNotifiedAt { get; set; }
    public DateTime? PaidAt { get; set; }
    public string? PaymentConfirmedByName { get; set; }

    public static readonly Expression<Func<Order, OrderExportRow>> Projection = o => new OrderExportRow
    {
        Id=o.Id, CreatedAt=o.CreatedAt, CustomerName=o.User.FullName, RecipientName=o.RecipientName,
        Phone=o.Phone, Address=o.Address, ItemKinds=o.Items.Count, Quantity=o.Items.Sum(i=>(long)i.Quantity),
        Total=o.Total, PaymentMethod=o.PaymentMethod, IsPaid=o.IsPaid, Status=o.Status,Subtotal=o.Subtotal,ShippingFee=o.ShippingFee,
        CustomerTransferNotifiedAt=o.CustomerTransferNotifiedAt,PaidAt=o.PaidAt,PaymentConfirmedByName=o.PaymentConfirmedByName
    };
}

public record ProductExportRow(int Id, string Name, string Category, decimal Price, int Stock);
public record DashboardExportReport(AdminDashboardViewModel Dashboard, IReadOnlyList<OrderExportRow> Orders);
