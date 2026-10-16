using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Controllers;

public abstract class ChatControllerBase(AppDbContext db) : Controller
{
    protected AppDbContext Db => db;
    protected async Task<IActionResult> ChatAsync(int id,bool admin,CancellationToken ct)
    {
        var conversation=await new ShopCommunication(db).Accessible(id,User,admin).Include(c=>c.Customer).Include(c=>c.AssignedAdmin).FirstOrDefaultAsync(ct);
        if(admin && conversation==null) return NotFound();
        return View("~/Views/Shared/ShopChat.cshtml",new ShopChatViewModel(conversation?.Id??0,admin?conversation!.Customer.FullName:"Chat với GreenShop",conversation?.Status??"Waiting",conversation?.AssignedAdminId,conversation?.Version??0){AssignedAdminName=conversation?.AssignedAdmin?.FullName});
    }
    protected async Task<IActionResult> MessagesAsync(int id,bool admin,long after,CancellationToken ct)
    {
        if(after<0) return BadRequest();Response.Headers.CacheControl="no-store";
        var identity=$"{ShoppingIdentity.UserId(User)}:{UserSession.Version(User)}";
        var conversation=await new ShopCommunication(db).Accessible(id,User,admin).Include(c=>c.AssignedAdmin).FirstOrDefaultAsync(ct);
        if(conversation==null) return admin ? NotFound() : Json(new {identity,conversationId=0,messages=Array.Empty<object>(),hasMore=false});
        var rows=await db.ShopMessages.AsNoTracking().Where(m=>m.ConversationId==conversation.Id && m.Id>after).OrderBy(m=>m.Id).Take(101)
            .Select(m=>new {m.Id,m.Content,m.FromAdmin,m.CreatedAt}).ToListAsync(ct);
        return Json(new {identity,conversationId=conversation.Id,status=conversation.Status,version=conversation.Version,assignedAdminId=admin?conversation.AssignedAdminId:null,assignedAdminName=admin?conversation.AssignedAdmin?.FullName:null,canReopen=admin && conversation.Status=="Resolved" && conversation.AssignedAdminId==ShoppingIdentity.UserId(User),canReply=admin ? (conversation.Status=="Waiting" && conversation.AssignedAdminId==null) || (conversation.Status=="InProgress" && conversation.AssignedAdminId==ShoppingIdentity.UserId(User)) : true,messages=rows.Take(100),hasMore=rows.Count>100});
    }
    protected async Task<IActionResult> SendAsync(int id,bool admin,MessageInput input,CancellationToken ct)
    {
        input.Content=input.Content?.Trim()??"";
        if(!ModelState.IsValid || input.Content.Length==0) return BadRequest(new {message="Nhập tin nhắn từ 1 đến 2.000 ký tự."});
        var result=await new ShopCommunication(db).SendAsync(id,User,admin,input,ct);
        if(result.Status==200) {
            var cid=await db.ShopMessages.Where(m=>m.Id==result.Id).Select(m=>m.ConversationId).SingleAsync(ct);
            var hub=HttpContext.RequestServices.GetRequiredService<Microsoft.AspNetCore.SignalR.IHubContext<GreenShop.Web.Hubs.SupportHub>>();
            // Cancellation of the original response cannot undo a committed message.
            try {await hub.Clients.Group("conversation:"+cid).SendCoreAsync("Changed",new object[]{cid},CancellationToken.None);}
            catch(Exception ex) when(ex is OperationCanceledException or IOException) {
                HttpContext.RequestServices.GetRequiredService<ILogger<ChatControllerBase>>()
                    .LogWarning("Support invalidation unavailable conversationId={ConversationId} category={Category}; persisted history remains readable",cid,ex.GetType().Name);
            }
        }
        if(result.Status==429) Response.Headers.RetryAfter="60";
        return result.Status==200 ? Json(new {id=result.Id}) : StatusCode(result.Status,new {message=result.Status==429?"Bạn gửi quá nhanh. Vui lòng đợi một phút.":result.Status==409?"Cuộc trò chuyện đã kết thúc hoặc do quản trị viên khác phụ trách. Vui lòng kiểm tra trạng thái mới.":"Chưa thể gửi tin nhắn. Hãy tải lại và thử lại."});
    }
    protected async Task<IActionResult> ReadAsync(int id,bool admin,long through,CancellationToken ct)
    {
        if(through<=0) return BadRequest();
        var conversation=await new ShopCommunication(db).Accessible(id,User,admin).Include(c=>c.AssignedAdmin).FirstOrDefaultAsync(ct);
        if(conversation==null) return NotFound();
        if(!await db.ShopMessages.AnyAsync(m=>m.ConversationId==conversation.Id && m.Id==through,ct)) return BadRequest();
        if(admin) {
            var aid=ShoppingIdentity.UserId(User);
            await db.Database.ExecuteSqlInterpolatedAsync($"INSERT INTO ShopConversationReads (ConversationId,AdminId,ThroughMessageId) VALUES ({conversation.Id},{aid},{through}) ON DUPLICATE KEY UPDATE ThroughMessageId=GREATEST(ThroughMessageId,{through})",ct);
        }
        else await db.ShopConversations.Where(c=>c.Id==conversation.Id && c.CustomerReadMessageId<through).ExecuteUpdateAsync(s=>s.SetProperty(c=>c.CustomerReadMessageId,through),ct);
        return NoContent();
    }
}
