using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc.ModelBinding;

namespace GreenShop.Web.Models;

public class AdminOrderFilter
{
    [StringLength(100)] public string? Search { get; set; }
    [Range(1,int.MaxValue)] public int? CustomerId { get; set; }
    public OrderStatus? Status { get; set; }
    [RegularExpression("^(COD|VIETQR)$")] public string? PaymentMethod { get; set; }
    [RegularExpression("^(unpaid|pending|paid)$")] public string? PaymentState { get; set; }
    public DateOnly? FromDate { get; set; }
    public DateOnly? ToDate { get; set; }
    public string Sort { get; set; } = "newest";
    [Range(1, int.MaxValue)] public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 15;
    public bool HasFilters => !string.IsNullOrEmpty(Search) || CustomerId.HasValue || Status.HasValue || FromDate.HasValue || ToDate.HasValue || Sort != "newest" || PaymentMethod!=null || PaymentState!=null;
}

public class AdminOrderRow
{
    public int Id { get; set; }
    public string CustomerName { get; set; } = string.Empty;
    public string RecipientName { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
    public decimal Total { get; set; }
    public long Quantity { get; set; }
    public OrderStatus Status { get; set; }
    public bool IsPaid { get; set; }
    public string PaymentMethod { get; set; } = string.Empty;
    public DateTime? CustomerTransferNotifiedAt { get; set; }
}

public class AdminOrderListViewModel
{
    public AdminOrderFilter Filter { get; set; } = new();
    public IReadOnlyList<AdminOrderRow> Orders { get; set; } = Array.Empty<AdminOrderRow>();
    public Dictionary<OrderStatus, int> Counts { get; set; } = new();
    public int Count(OrderStatus status) => Counts.GetValueOrDefault(status);
    public int TotalCount => Counts.Values.Sum();
    public int MatchingCount { get; set; }
    public int TotalPages => Math.Max(1, (int)Math.Ceiling(MatchingCount / (double)Filter.PageSize));
}

public class AdminOrderDetailViewModel
{
    public Order Order { get; set; } = null!;
    public bool Print { get; set; }
    public decimal ItemsTotal => Order.Items.Sum(i => i.UnitPrice * i.Quantity);
    public bool ValidTotal => PaymentMethods.ValidMoney(Order);
}

public class AdminOrderCommand
{
    [BindRequired, Range(0, long.MaxValue - 1)] public long ExpectedVersion { get; set; }
    [StringLength(1000)] public string? Note { get; set; }
}

public class AdminOrderTransition : AdminOrderCommand
{
    [BindRequired] public OrderStatus TargetStatus { get; set; }
}

public class AdminDashboardOrders
{
    public int PendingCount { get; set; }
    public decimal PaidOrderValueThisMonth { get; set; }
    public int UserCount { get; set; }
}
