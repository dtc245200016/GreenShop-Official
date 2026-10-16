using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc.ModelBinding;

namespace GreenShop.Web.Models;

public class HomeSliderSettings
{
    public int Id { get; set; } = 1;
    [Required, RegularExpression("^(bestsellers|all)$")] public string Mode { get; set; } = "bestsellers";
    [Range(1,100)] public int ProductCount { get; set; } = 5;
    [Range(0,3650)] public int Days { get; set; } = 30;
    [BindRequired, Range(0,long.MaxValue-1)] public long Version { get; set; }
}

public class ProductReview
{
    public int Id { get; set; }
    public int OrderItemId { get; set; }
    public OrderItem OrderItem { get; set; } = null!;
    public int UserId { get; set; }
    public User User { get; set; } = null!;
    public int? ProductId { get; set; }
    public Product? Product { get; set; }
    [MaxLength(150)] public string ProductName { get; set; } = "";
    public int Stars { get; set; }
    [MaxLength(1500)] public string Content { get; set; } = "";
    [MaxLength(255)] public string? Image1 { get; set; }
    [MaxLength(255)] public string? Image2 { get; set; }
    [MaxLength(255)] public string? Image3 { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? AdminReadAt { get; set; } // Historical global receipt; new notifications are per recipient.
    [MaxLength(255)] public string? Image4 { get; set; }
    [MaxLength(255)] public string? Image5 { get; set; }
    public bool IsCurrent { get; set; } = true;
    public bool IsHidden { get; set; }
    public int? CurrentProductId { get; private set; }
    public DateTime? UpdatedAt { get; set; }
    public long Version { get; set; }
    [MaxLength(1500)] public string? ReplyContent { get; set; }
    public int? ReplyAdminId { get; set; }
    public DateTime? ReplyCreatedAt { get; set; }
    public DateTime? ReplyUpdatedAt { get; set; }
}

public class ShopConversation
{
    public int Id { get; set; }
    public int CustomerId { get; set; }
    public User Customer { get; set; } = null!;
    public long CustomerReadMessageId { get; set; }
    public long AdminReadMessageId { get; set; }
    public DateTime UpdatedAt { get; set; }
    public int? AssignedAdminId { get; set; }
    public User? AssignedAdmin { get; set; }
    [MaxLength(20)] public string Status { get; set; } = "Waiting";
    public long Version { get; set; }
}

public class ShopMessage
{
    public long Id { get; set; }
    public int ConversationId { get; set; }
    public ShopConversation Conversation { get; set; } = null!;
    public int SenderId { get; set; }
    public User Sender { get; set; } = null!;
    public bool FromAdmin { get; set; }
    [MaxLength(2000)] public string Content { get; set; } = "";
    [MaxLength(32)] public string RequestToken { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}

public class ReviewInput
{
    [BindRequired, Range(1,5,ErrorMessage="Vui lòng chọn từ 1 đến 5 sao.")] public int Stars { get; set; }
    [Required(ErrorMessage="Vui lòng nhập nhận xét."), StringLength(1500,MinimumLength=3)] public string Content { get; set; } = "";
    public List<IFormFile> Photos { get; set; } = new();
    [Range(0,long.MaxValue-1)] public long Version { get; set; }
    [BindNever] public bool Editing { get; set; }
    [Range(0,int.MaxValue)] public int ReviewId { get; set; }
    [BindNever] public int OrderId { get; set; }
    [BindNever] public int OrderItemId { get; set; }
    [BindNever] public string ProductName { get; set; } = "";
}

public class MessageInput
{
    [Required, StringLength(2000,MinimumLength=1)] public string Content { get; set; } = "";
    [Required, RegularExpression("^[a-f0-9]{32}$")] public string RequestToken { get; set; } = "";
}

public class ReviewReplyInput
{
    [Required(ErrorMessage="Vui lòng nhập phản hồi."), StringLength(1500,MinimumLength=3,ErrorMessage="Phản hồi cần từ 3 đến 1500 ký tự.")]
    public string Content { get; set; } = "";
    [BindRequired,Range(0,long.MaxValue-1)] public long Version { get; set; }
}

public record ShopAlertCounts(int Orders, int Messages, int Reviews, int Notifications = 0)
{
    public int Total => Notifications;
}
public record ShopChatViewModel(int ConversationId, string Title, string Status="Waiting", int? AssignedAdminId=null, long Version=0)
{
    public string? AssignedAdminName { get; init; }
}
public record ShopInboxViewModel(IReadOnlyList<ShopConversation> Conversations, int Page, bool HasNext)
{
    public IReadOnlyDictionary<int,int> Unread { get; init; } = new Dictionary<int,int>();
}
public record ShopReviewProduct
{
    public int Id { get; init; }
    public string Name { get; init; } = "";
    public string ImageUrl { get; init; } = "";
    public string CategoryName { get; init; } = "";
    public int ReviewCount { get; init; }
    public int UnreadCount { get; init; }
    public double? AverageStars { get; init; }
    public DateTime? LatestAt { get; init; }
}
public record ShopReviewsViewModel(IReadOnlyList<ProductReview> Reviews, int Page, bool HasNext)
{
    public bool IsProductIndex { get; init; }
    public IReadOnlyList<ShopReviewProduct> Products { get; init; } = Array.Empty<ShopReviewProduct>();
    public IReadOnlyList<Category> Categories { get; init; } = Array.Empty<Category>();
    public IReadOnlySet<int> UnreadIds { get; init; } = new HashSet<int>();
    public int? ProductId { get; init; }
    public int? ReviewId { get; init; }
    public string ProductName { get; init; } = "";
    public string Search { get; init; } = "";
    public int? CategoryId { get; init; }
    public int? Stars { get; init; }
    public string Scope { get; init; } = "all";
    public string Visibility { get; init; } = "all";
    public int ArchivedCount { get; init; }
    public int ArchivedUnreadCount { get; init; }
}

public class ShopConversationRead
{
    public int ConversationId { get; set; }
    public ShopConversation Conversation { get; set; } = null!;
    public int AdminId { get; set; }
    public User Admin { get; set; } = null!;
    public long ThroughMessageId { get; set; }
}

public class AdminNotification
{
    public long Id { get; set; }
    public int RecipientId { get; set; }
    public User Recipient { get; set; } = null!;
    [MaxLength(100)] public string EventKey { get; set; } = "";
    [MaxLength(20)] public string Kind { get; set; } = "";
    [MaxLength(150)] public string Title { get; set; } = "";
    [MaxLength(255)] public string Link { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public DateTime? ReadAt { get; set; }
}
