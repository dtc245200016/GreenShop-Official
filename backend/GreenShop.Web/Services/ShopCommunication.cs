using System.Data;
using System.Security.Claims;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public class ShopCommunication(AppDbContext db)
{
    public static async Task<ShopAlertCounts> AlertsAsync(AppDbContext db,int adminId,CancellationToken ct) => new(
        await db.Orders.CountAsync(o=>o.Status==OrderStatus.Pending,ct),
        await db.ShopMessages.CountAsync(m=>!m.FromAdmin && m.Id>(db.ShopConversationReads.Where(r=>r.ConversationId==m.ConversationId && r.AdminId==adminId).Select(r=>(long?)r.ThroughMessageId).FirstOrDefault()??0),ct),
        await db.ProductReviews.CountAsync(r=>db.AdminNotifications.Any(n=>n.RecipientId==adminId && n.Kind=="Review" && n.ReadAt==null && n.EventKey.StartsWith("review:"+r.Id+":")),ct),
        await db.AdminNotifications.CountAsync(n=>n.RecipientId==adminId && n.ReadAt==null,ct));

    public IQueryable<ShopConversation> Accessible(int conversationId,ClaimsPrincipal user,bool admin) =>
        db.ShopConversations.AsNoTracking().Where(c=>admin ? c.Id==conversationId : c.CustomerId==ShoppingIdentity.UserId(user));

    public Task<(int Status,long Id)> SendAsync(int conversationId,ClaimsPrincipal user,bool admin,MessageInput input,CancellationToken ct) =>
        db.Database.CreateExecutionStrategy().ExecuteAsync(async () => {
            db.ChangeTracker.Clear();
            await using var tx=await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted,ct);
            var actor=await ShoppingIdentity.LockUserAsync(db,ShoppingIdentity.UserId(user),ct);
            if(actor==null || !actor.IsActive || actor.Role!=(admin?UserRole.Admin:UserRole.Customer) || actor.SessionVersion!=UserSession.Version(user)) return (403,0L);
            var conversation=await Accessible(conversationId,user,admin).FirstOrDefaultAsync(ct);
            if(conversation==null && admin) return (404,0L);
            if(conversation!=null) conversation=(await db.ShopConversations.FromSqlInterpolated($"SELECT * FROM ShopConversations WHERE Id={conversation.Id} FOR UPDATE").ToListAsync(ct)).Single();
            var retry=await db.ShopMessages.AsNoTracking().FirstOrDefaultAsync(m=>m.SenderId==actor.Id && m.RequestToken==input.RequestToken,ct);
            if(retry!=null) return conversation?.Id==retry.ConversationId && retry.Content==input.Content ? (200,retry.Id) : (409,0L);
            // The first reply claims a waiting conversation atomically under its row lock.
            // Another active assignee must still be respected, including simultaneous replies.
            if(admin && conversation!.Status=="Waiting" && conversation.AssignedAdminId==null) {
                conversation.Status="InProgress";conversation.AssignedAdminId=actor.Id;conversation.Version++;
            }
            if(admin && (conversation!.AssignedAdminId!=actor.Id || conversation.Status!="InProgress")) return (409,0L);
            var cutoff=DateTime.UtcNow.AddMinutes(-1);
            if(await db.ShopMessages.CountAsync(m=>m.SenderId==actor.Id && m.CreatedAt>=cutoff,ct)>=20) return (429,0L);
            if(conversation==null) {
                conversation=new ShopConversation{CustomerId=actor.Id,UpdatedAt=DateTime.UtcNow};
                db.ShopConversations.Add(conversation);await db.SaveChangesAsync(ct);
            }
            if(!admin && conversation.Status=="Resolved") {conversation.Status="Waiting";conversation.AssignedAdminId=null;conversation.Version++;}
            conversation.UpdatedAt=DateTime.UtcNow;
            var message=new ShopMessage{ConversationId=conversation.Id,SenderId=actor.Id,FromAdmin=admin,Content=input.Content,RequestToken=input.RequestToken,CreatedAt=DateTime.UtcNow};
            db.ShopMessages.Add(message);await db.SaveChangesAsync(ct);
            if(!admin) await AdminNotifications.AddAsync(db,"message:"+message.Id,"Message","Tin nhắn hỗ trợ mới","/Admin/KhachHang/TroChuyen/"+conversation.Id,ct);
            await tx.CommitAsync(ct);return (200,message.Id);
        });
}
