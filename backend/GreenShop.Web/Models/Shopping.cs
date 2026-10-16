namespace GreenShop.Web.Models;

public class CartItem
{
    public int Id { get; set; }
    public int UserId { get; set; }
    public User User { get; set; } = null!;
    public int ProductId { get; set; }
    public Product Product { get; set; } = null!;
    public int Quantity { get; set; }
}

// Preserve persisted values 0/1/2 and the existing Completed sold-count query.
public enum OrderStatus { Pending = 0, Completed = 1, Cancelled = 2, Confirmed = 3, Processing = 4, Shipping = 5 }
public enum OrderInventoryStatus { Unverified = 0, Deducted = 1, Restored = 2 }
public enum OrderHistoryKind { Status = 0, Note = 1, Payment = 2, Inventory = 3, CustomerTransfer = 4 }

public class Order
{
    public int Id { get; set; }
    public int UserId { get; set; }
    public User User { get; set; } = null!;
    public string ConfirmationToken { get; set; } = string.Empty;
    public string RecipientName { get; set; } = string.Empty;
    public string Phone { get; set; } = string.Empty;
    public string Address { get; set; } = string.Empty;
    public DateTime CreatedAt { get; set; }
    public decimal Total { get; set; }
    public OrderStatus Status { get; set; } = OrderStatus.Pending;
    public bool IsPaid { get; set; }
    public string PaymentMethod { get; set; } = "COD";
    // Nullable for historical orders: never invent an unrecorded monetary/payment breakdown.
    public decimal? Subtotal { get; set; }
    public decimal? ShippingFee { get; set; }
    public decimal? ShippingFlatFeeSnapshot { get; set; }
    public decimal? FreeShippingThresholdSnapshot { get; set; }
    public string? BankBinSnapshot { get; set; }
    public string? BankNameSnapshot { get; set; }
    public string? BankAccountSnapshot { get; set; }
    public string? BankHolderSnapshot { get; set; }
    public string? TransferContent { get; set; }
    public DateTime? CustomerTransferNotifiedAt { get; set; }
    public DateTime? PaidAt { get; set; }
    public int? PaymentConfirmedById { get; set; }
    public User? PaymentConfirmedBy { get; set; }
    public string? PaymentConfirmedByName { get; set; }
    public long Version { get; set; }
    public OrderInventoryStatus InventoryStatus { get; set; } = OrderInventoryStatus.Unverified;
    public string AdminNote { get; set; } = string.Empty;
    public ICollection<OrderItem> Items { get; set; } = new List<OrderItem>();
    public ICollection<OrderStatusHistory> History { get; set; } = new List<OrderStatusHistory>();
}

public class OrderStatusHistory
{
    public int Id { get; set; }
    public int OrderId { get; set; }
    public Order Order { get; set; } = null!;
    public OrderHistoryKind Kind { get; set; }
    public OrderStatus? FromStatus { get; set; }
    public OrderStatus? ToStatus { get; set; }
    public DateTime CreatedAt { get; set; }
    public int? AdminId { get; set; }
    public User? Admin { get; set; }
    public string AdminName { get; set; } = string.Empty;
    public string Note { get; set; } = string.Empty;
}

public class OrderItem
{
    public int Id { get; set; }
    public int OrderId { get; set; }
    public Order Order { get; set; } = null!;
    public int? ProductId { get; set; }
    public Product? Product { get; set; }
    // Snapshots preserve the receipt when Admin edits or deletes a product.
    public string ProductName { get; set; } = string.Empty;
    public string ImageUrl { get; set; } = string.Empty;
    public decimal UnitPrice { get; set; }
    public int Quantity { get; set; }
}
