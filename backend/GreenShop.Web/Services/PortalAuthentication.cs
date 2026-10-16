using System.Security.Claims;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;

namespace GreenShop.Web.Services;

public static class PortalAuthentication
{
    public const string PolicyScheme = "GreenShop.Portal";
    // Keep the existing scheme/name/key purpose for genuine pre-upgrade Admin cookies.
    public const string AdminScheme = CookieAuthenticationDefaults.AuthenticationScheme;
    public const string AdminCookie = ".AspNetCore.Cookies";
    public const string CustomerScheme = "GreenShop.Customer";
    public const string CustomerCookie = "GreenShop.Customer";
    public const string MigratedCustomerItem = "GreenShop.MigratedCustomer";
    public const string StorefrontAdminItem = "GreenShop.StorefrontAdmin";
    public const string PreviewParameter = "portal";
    public const string CustomerLoginRoute = "CustomerLogin";
    public const string AdminLoginRoute = "AdminLogin";
    public const string CustomerLogoutRoute = "CustomerLogout";
    public const string AdminLogoutRoute = "AdminLogout";

    public static bool IsAdmin(HttpRequest request) => request.Path.StartsWithSegments("/Admin", StringComparison.OrdinalIgnoreCase);
    public static string Scheme(HttpRequest request) => IsAdmin(request) ? AdminScheme : CustomerScheme;

    public static string? SafeReturnUrl(string? value, bool admin)
    {
        if(!admin) return ShoppingIdentity.SafeReturnUrl(value);
        if(string.IsNullOrEmpty(value) || value.Length>2000 || !value.StartsWith('/') || value.StartsWith("//") || value.Contains('\\') || value.Any(char.IsControl)) return null;
        var path=value.Split('?', '#')[0];
        // Existing Admin GET pages only. Never redirect a sign-in to a mutation endpoint.
        return Regex.IsMatch(path,
            @"^/Admin(?:/(?:Admin/(?:Index|TongQuan)|DonHang/(?:QuanLyDonHang|ChiTietDonHang/[1-9][0-9]*|InDonHang/[1-9][0-9]*)|NguoiDung/(?:QuanLyNguoiDung|ChiTietNguoiDung/[1-9][0-9]*)|SanPham/(?:QuanLySanPham|ThemSanPham|SuaSanPham/[1-9][0-9]*|XoaSanPham/[1-9][0-9]*)|DanhMuc/(?:QuanLyDanhMuc|ThemDanhMuc|SuaDanhMuc/[1-9][0-9]*|XoaDanhMuc/[1-9][0-9]*)|CaiDatCuaHang/QuanLyThanhToanVanChuyen))?/?$",
            RegexOptions.IgnoreCase) ? value : null;
    }

    public static async Task MigrateLegacyCustomerAsync(HttpContext context)
    {
        if(!IsAdmin(context.Request) && !context.Request.Path.StartsWithSegments("/Account")
            && (!context.Request.Cookies.ContainsKey(CustomerCookie)
                || context.Request.Query[PreviewParameter]=="admin")
            && context.Request.Cookies.ContainsKey(AdminCookie))
        {
            // Reuse the genuine, DB-validated Admin ticket. The query selects a view,
            // never a role; ordinary Customer tabs keep their own existing cookie.
            var result=await context.AuthenticateAsync(AdminScheme);
            if(result.Succeeded && result.Principal?.IsInRole("Admin")==true)
                context.Items[StorefrontAdminItem]=result.Principal;
        }
    }

    public static void RestoreMigratedCustomer(HttpContext context)
    {
        if(!IsAdmin(context.Request) && context.Items.TryGetValue(StorefrontAdminItem,out var admin)
            && admin is ClaimsPrincipal adminPrincipal)
        {
            context.User=adminPrincipal;
            return;
        }
        if(!IsAdmin(context.Request) && context.User.Identity?.IsAuthenticated!=true
            && context.Items.TryGetValue(MigratedCustomerItem,out var principal) && principal is ClaimsPrincipal customer)
            context.User=customer;
    }
}
