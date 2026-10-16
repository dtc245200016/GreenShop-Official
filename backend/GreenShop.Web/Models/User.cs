using System.ComponentModel.DataAnnotations;

namespace GreenShop.Web.Models
{
    public static class ShopOwnership
    {
        public const string OwnerEmail = "trungdtt123@gmail.com";
        public static bool IsOwnerEmail(string? email) => string.Equals(email?.Trim(),OwnerEmail,StringComparison.OrdinalIgnoreCase);
    }

    public enum UserRole
    {
        Customer = 0,
        Admin = 1
    }

    public class User
    {
        public int Id { get; set; }

        [Required(ErrorMessage = "Vui lòng nhập họ và tên")]
        [StringLength(100)]
        public string FullName { get; set; } = string.Empty;

        [Required(ErrorMessage = "Vui lòng nhập Email")]
        [EmailAddress(ErrorMessage = "Email không hợp lệ")]
        public string Email { get; set; } = string.Empty;

        [Required(ErrorMessage = "Vui lòng nhập mật khẩu")]
        public string PasswordHash { get; set; } = string.Empty;

        public string Phone { get; set; } = string.Empty;

        public UserRole Role { get; set; } = UserRole.Customer;

        public bool IsActive { get; set; } = true;
        public long Version { get; set; }
        public long SessionVersion { get; set; }

        public DateTime CreatedAt { get; set; } = DateTime.UtcNow;
    }

    public class RegisterViewModel
    {
        [Required(ErrorMessage = "Họ và tên không được để trống")]
        [StringLength(100,ErrorMessage="Họ tên tối đa 100 ký tự.")]
        public string FullName { get; set; } = string.Empty;

        [Required(ErrorMessage = "Email không được để trống")]
        [EmailAddress(ErrorMessage = "Định dạng Email không đúng")]
        [StringLength(255)]
        public string Email { get; set; } = string.Empty;

        [StringLength(21,ErrorMessage="Số điện thoại tối đa 21 ký tự.")]
        public string Phone { get; set; } = string.Empty;

        [Required(ErrorMessage = "Mật khẩu không được để trống")]
        [MinLength(6, ErrorMessage = "Mật khẩu tối thiểu 6 ký tự")]
        [StringLength(256)]
        public string Password { get; set; } = string.Empty;

        [Required(ErrorMessage = "Xác nhận mật khẩu không được để trống")]
        [Compare("Password", ErrorMessage = "Mật khẩu xác nhận không khớp")]
        public string ConfirmPassword { get; set; } = string.Empty;
    }

    public class LoginViewModel
    {
        [Required(ErrorMessage = "Vui lòng nhập Email")]
        [EmailAddress(ErrorMessage = "Email không đúng định dạng")]
        [StringLength(255)]
        public string Email { get; set; } = string.Empty;

        [Required(ErrorMessage = "Vui lòng nhập mật khẩu")]
        [StringLength(1024)]
        public string Password { get; set; } = string.Empty;

        public bool RememberMe { get; set; }
    }
}
