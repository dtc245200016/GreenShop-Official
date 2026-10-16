using System.ComponentModel.DataAnnotations;
using Microsoft.AspNetCore.Mvc.ModelBinding;

namespace GreenShop.Web.Models;

public class AdminUserFilter
{
    [StringLength(100)] public string? Search { get; set; }
    public UserRole? Role { get; set; }
    public bool? Active { get; set; }
    public string Sort { get; set; } = "newest";
    [Range(1, int.MaxValue)] public int Page { get; set; } = 1;
    public int PageSize { get; set; } = 15;
}

// PasswordHash and session identifiers deliberately never enter display models.
public class AdminUserRow
{
    public int Id { get; set; }
    public string FullName { get; set; } = "";
    public string Email { get; set; } = "";
    public string Phone { get; set; } = "";
    public UserRole Role { get; set; }
    public bool IsActive { get; set; }
    public DateTime CreatedAt { get; set; }
    public int OrderCount { get; set; }
    public long Version { get; set; }
    public bool IsShopOwner => Role==UserRole.Admin && ShopOwnership.IsOwnerEmail(Email);
    public string RoleLabel => IsShopOwner ? "Chủ shop" : Role == UserRole.Admin ? "Quản trị viên" : Role == UserRole.Customer ? "Khách hàng" : "Chưa có quyền hợp lệ";
    public string Initial => string.IsNullOrWhiteSpace(FullName) ? "?" : System.Globalization.StringInfo.GetNextTextElement(FullName.Trim()).ToUpperInvariant();
}

public class AdminUserListViewModel
{
    public AdminUserFilter Filter { get; set; } = new();
    public IReadOnlyList<AdminUserRow> Users { get; set; } = Array.Empty<AdminUserRow>();
    public int Total { get; set; }
    public int Customers { get; set; }
    public int Administrators { get; set; }
    public int Active { get; set; }
    public int Locked { get; set; }
    public int MatchingCount { get; set; }
    public int TotalPages => Math.Max(1,(int)Math.Ceiling(MatchingCount/(double)Filter.PageSize));
}

public class AdminUserDetailViewModel
{
    public AdminUserRow Account { get; set; } = null!;
    public bool IsSelf { get; set; }
    public bool IsLastAdmin { get; set; }
    public bool CanEditProfile { get; init; }
    public bool CanChangeRole { get; init; }
    public bool CanChangeStatus { get; init; }
    public AdminUserProfile? SubmittedProfile { get; set; }
}

public class AdminUserCommand
{
    [BindRequired,Range(0,long.MaxValue-1)] public long ExpectedVersion { get; set; }
}
public class AdminUserProfile : AdminUserCommand
{
    [Required(ErrorMessage="Vui lòng nhập họ tên."),StringLength(100,ErrorMessage="Họ tên tối đa 100 ký tự.")] public string FullName { get; set; } = "";
    [StringLength(21,ErrorMessage="Số điện thoại tối đa 21 ký tự."),RegularExpression(@"^[+0-9 ()-]*$",ErrorMessage="Số điện thoại không hợp lệ.")] public string? Phone { get; set; }
}
public class AdminUserRoleCommand : AdminUserCommand
{
    [BindRequired] public UserRole TargetRole { get; set; }
}
