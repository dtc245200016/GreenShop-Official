using System.Security.Claims;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public static class ShoppingIdentity
{
    public static int UserId(ClaimsPrincipal user) => int.TryParse(user.FindFirstValue(ClaimTypes.NameIdentifier), out var id) && id > 0 ? id : 0;

    // Serialize a user's cart writes and checkout retries without trusting client UserId.
    public static async Task<User?> LockUserAsync(AppDbContext db, int id, CancellationToken ct) =>
        (await db.Users.FromSqlInterpolated($"SELECT * FROM Users WHERE Id = {id} FOR UPDATE").AsNoTracking().ToListAsync(ct)).SingleOrDefault();

    public static string? SafeReturnUrl(string? value)
    {
        if (string.IsNullOrEmpty(value) || value.Length > 2000 || !value.StartsWith('/') || value.StartsWith("//") || value.Contains('\\') || value.Any(char.IsControl)) return null;
        var path = value.Split('?', '#')[0];
        // Only existing GET pages; never send a login back to a mutation endpoint.
        return System.Text.RegularExpressions.Regex.IsMatch(path,
            @"^/(?:Home(?:/Index)?|SanPham/(?:CuaHang|ChiTietSanPham/[1-9][0-9]*)|GioHang/QuanLyGioHang|TuongTac/(?:TroChuyen|DanhGia/[1-9][0-9]*)|ThanhToan/(?:XacNhanMuaHang/[1-9][0-9]*|XacNhanGioHang|ThanhToanVietQR/[1-9][0-9]*|DonHangCuaToi|ChiTietDonHang/[1-9][0-9]*))?/?$",
            System.Text.RegularExpressions.RegexOptions.IgnoreCase) ? value : null;
    }
}
