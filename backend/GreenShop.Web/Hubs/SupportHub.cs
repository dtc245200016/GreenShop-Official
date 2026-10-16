using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Hubs;

// The hub carries invalidations only. Content is fetched through session-validated,
// owner-authorized HTTP; writes use existing antiforgery-protected POST endpoints.
[Authorize(Roles="Admin,Customer")]
public class SupportHub(AppDbContext db) : Hub
{
    public async Task JoinConversation(int id)
    {
        var user=Context.User!;var uid=ShoppingIdentity.UserId(user);
        var actor=await db.Users.AsNoTracking().FirstOrDefaultAsync(u=>u.Id==uid,Context.ConnectionAborted);
        if(actor==null || !actor.IsActive || actor.SessionVersion!=UserSession.Version(user) || actor.Role.ToString()!=user.FindFirst(System.Security.Claims.ClaimTypes.Role)?.Value)
            throw new HubException("Session expired");
        var conversation=await new ShopCommunication(db).Accessible(id,user,user.IsInRole("Admin")).FirstOrDefaultAsync(Context.ConnectionAborted);
        if(conversation==null || conversation.Id!=id) throw new HubException("Conversation unavailable");
        await Groups.AddToGroupAsync(Context.ConnectionId,"conversation:"+conversation.Id);
    }
}
