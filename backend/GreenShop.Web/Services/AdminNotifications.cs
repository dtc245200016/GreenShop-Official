using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public static class AdminNotifications
{
    // Called inside the originating transaction. Retry returns the existing order/message,
    // while the recipient/event unique key provides a second duplicate guard.
    public static async Task AddAsync(AppDbContext db,string key,string kind,string title,string link,CancellationToken ct)
    {
        var recipients=await db.Users.Where(u=>u.IsActive && u.Role==UserRole.Admin).Select(u=>u.Id).ToListAsync(ct);
        foreach(var id in recipients) db.AdminNotifications.Add(new AdminNotification {
            RecipientId=id,EventKey=key,Kind=kind,Title=title,Link=link,CreatedAt=DateTime.UtcNow
        });
        await db.SaveChangesAsync(ct);
    }
}
