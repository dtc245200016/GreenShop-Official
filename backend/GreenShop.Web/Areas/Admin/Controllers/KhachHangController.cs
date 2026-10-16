using GreenShop.Web.Controllers;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.ModelBinding;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Areas.Admin.Controllers;

[Area("Admin"),Authorize(Roles="Admin")]
public class KhachHangController(AppDbContext db) : ChatControllerBase(db)
{
    [HttpGet] public async Task<IActionResult> Slider(CancellationToken ct)=>View(await Db.HomeSliderSettings.AsNoTracking().SingleAsync(ct));
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> Slider(HomeSliderSettings input,CancellationToken ct)
    {
        if(!ModelState.IsValid) {Response.StatusCode=400;return View(input);}
        var changed=await Db.HomeSliderSettings.Where(s=>s.Id==1 && s.Version==input.Version).ExecuteUpdateAsync(s=>s.SetProperty(s=>s.Mode,input.Mode).SetProperty(s=>s.ProductCount,input.ProductCount).SetProperty(s=>s.Days,input.Days).SetProperty(s=>s.Version,s=>s.Version+1),ct);
        if(changed==0) {Response.StatusCode=409;ModelState.Clear();ModelState.AddModelError("","Cấu hình vừa được thay đổi. Kiểm tra dữ liệu mới rồi lưu lại.");return View(await Db.HomeSliderSettings.AsNoTracking().SingleAsync(ct));}
        TempData["SuccessMessage"]="Đã cập nhật slider trang chủ.";return RedirectToAction(nameof(Slider));
    }
    [HttpGet] public async Task<IActionResult> ThongBao(CancellationToken ct) {Response.Headers.CacheControl="no-store";return Json(await ShopCommunication.AlertsAsync(Db,ShoppingIdentity.UserId(User),ct));}
    [HttpGet] public async Task<IActionResult> TinNhan(int page=1,CancellationToken ct=default)
    {
        if(page<1 || page>100000) return BadRequest();
        var rows=await Db.ShopConversations.AsNoTracking().Include(c=>c.Customer).OrderByDescending(c=>c.UpdatedAt).ThenByDescending(c=>c.Id).Skip((page-1)*20).Take(21).ToListAsync(ct);
        var ids=rows.Take(20).Select(c=>c.Id).ToArray();
        var unread=await Db.ShopMessages.Where(m=>ids.Contains(m.ConversationId) && !m.FromAdmin && m.Id>(Db.ShopConversationReads.Where(r=>r.ConversationId==m.ConversationId && r.AdminId==ShoppingIdentity.UserId(User)).Select(r=>(long?)r.ThroughMessageId).FirstOrDefault()??0)).GroupBy(m=>m.ConversationId).Select(g=>new{Id=g.Key,Count=g.Count()}).ToDictionaryAsync(g=>g.Id,g=>g.Count,ct);
        return View(new ShopInboxViewModel(rows.Take(20).ToList(),page,rows.Count>20){Unread=unread});
    }
    [HttpGet] public Task<IActionResult> TroChuyen([FromRoute]int id,CancellationToken ct)=>ChatAsync(id,true,ct);
    [HttpGet] public Task<IActionResult> TinNhanMoi([FromRoute]int id,long after=0,CancellationToken ct=default)=>MessagesAsync(id,true,after,ct);
    [HttpPost,ValidateAntiForgeryToken] public Task<IActionResult> GuiTinNhan([FromRoute]int id,MessageInput input,CancellationToken ct)=>SendAsync(id,true,input,ct);
    [HttpPost,ValidateAntiForgeryToken] public Task<IActionResult> DaDoc([FromRoute]int id,long through,CancellationToken ct)=>ReadAsync(id,true,through,ct);
    [HttpGet] public async Task<IActionResult> DanhGia(int page=1,int? reviewId=null,int? productId=null,string? search=null,int? categoryId=null,int? stars=null,string scope="all",string visibility="all",CancellationToken ct=default)
    {
        search=search?.Trim()??"";
        if(!ModelState.IsValid || page<1 || page>100000 || reviewId is <=0 || productId is <0 || categoryId is <=0 || stars is <1 or >5 || search.Length>150
            || scope is not ("all" or "unread" or "with-reviews") || visibility is not ("all" or "public" or "hidden" or "archived")) return BadRequest();
        Response.Headers.CacheControl="no-store";
        var uid=ShoppingIdentity.UserId(User);
        var unread=Db.ProductReviews.AsNoTracking().Where(r=>Db.AdminNotifications.Any(n=>n.RecipientId==uid && n.Kind=="Review" && n.ReadAt==null && n.EventKey.StartsWith("review:"+r.Id+":")));
        var reviews=Db.ProductReviews.AsNoTracking().AsQueryable();
        if(stars!=null) reviews=reviews.Where(r=>r.Stars==stars);
        if(visibility=="public") reviews=reviews.Where(r=>r.IsCurrent && !r.IsHidden);
        if(visibility=="hidden") reviews=reviews.Where(r=>r.IsHidden);
        if(visibility=="archived") reviews=reviews.Where(r=>!r.IsCurrent);
        if(scope=="unread") reviews=reviews.Where(r=>unread.Any(u=>u.Id==r.Id));
        if(productId!=null || reviewId!=null) {
            var name="Sản phẩm đã xóa";
            if(reviewId!=null) {
                var target=await Db.ProductReviews.AsNoTracking().Where(r=>r.Id==reviewId).Select(r=>new{r.ProductId,r.ProductName}).FirstOrDefaultAsync(ct);
                if(target==null)return NotFound();
                if(productId!=null && productId!=(target.ProductId??0))return BadRequest();
                productId=target.ProductId??0;name=target.ProductName;reviews=reviews.Where(r=>r.Id==reviewId);
            }
            if(productId>0) {
                var product=await Db.Products.AsNoTracking().Where(p=>p.Id==productId).Select(p=>p.Name).FirstOrDefaultAsync(ct);
                if(product==null)return NotFound();name=product;
            }
            reviews=productId==0?reviews.Where(r=>r.ProductId==null):reviews.Where(r=>r.ProductId==productId);
            if(search.Length>0)reviews=reviews.Where(r=>r.Content.Contains(search) || r.User.FullName.Contains(search));
            var rows=await reviews.Include(r=>r.User).OrderByDescending(r=>r.Id).Skip((page-1)*20).Take(21).ToListAsync(ct);
            var ids=rows.Take(20).Select(r=>r.Id).ToArray();
            return View(new ShopReviewsViewModel(rows.Take(20).ToList(),page,rows.Count>20){ProductId=productId,ProductName=name,ReviewId=reviewId,Search=search,Stars=stars,Scope=scope,Visibility=visibility,
                UnreadIds=(await unread.Where(r=>ids.Contains(r.Id)).Select(r=>r.Id).ToListAsync(ct)).ToHashSet()});
        }
        var products=Db.Products.AsNoTracking().AsQueryable();
        if(search.Length>0)products=products.Where(p=>p.Name.Contains(search));
        if(categoryId!=null)products=products.Where(p=>p.CategoryId==categoryId);
        var projected=products.Select(p=>new ShopReviewProduct{Id=p.Id,Name=p.Name,ImageUrl=p.ImageUrl,CategoryName=p.Category==null?"Chưa phân loại":p.Category.Name,
            ReviewCount=reviews.Count(r=>r.ProductId==p.Id),UnreadCount=unread.Count(r=>r.ProductId==p.Id),
            AverageStars=Db.ProductReviews.Where(r=>r.ProductId==p.Id && r.IsCurrent && !r.IsHidden).Average(r=>(double?)r.Stars),
            LatestAt=reviews.Where(r=>r.ProductId==p.Id).Max(r=>(DateTime?)(r.UpdatedAt??r.CreatedAt))});
        if(scope=="unread")projected=projected.Where(p=>p.UnreadCount>0 && p.ReviewCount>0);
        else if(scope=="with-reviews" || stars!=null || visibility!="all")projected=projected.Where(p=>p.ReviewCount>0);
        var list=await projected.OrderByDescending(p=>p.UnreadCount).ThenByDescending(p=>p.LatestAt).ThenBy(p=>p.Id).Skip((page-1)*20).Take(21).ToListAsync(ct);
        return View(new ShopReviewsViewModel(Array.Empty<ProductReview>(),page,list.Count>20){IsProductIndex=true,Products=list.Take(20).ToList(),Search=search,CategoryId=categoryId,Stars=stars,Scope=scope,Visibility=visibility,
            Categories=await Db.Categories.AsNoTracking().OrderBy(c=>c.Name).ToListAsync(ct),
            ArchivedCount=await Db.ProductReviews.CountAsync(r=>r.ProductId==null,ct),ArchivedUnreadCount=await unread.CountAsync(r=>r.ProductId==null,ct)});
    }
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> DaDocDanhGia([FromRoute]int id,string? returnUrl,CancellationToken ct)
    {
        if(!await Db.ProductReviews.AnyAsync(r=>r.Id==id,ct)) return NotFound();
        var uid=ShoppingIdentity.UserId(User);
        await Db.AdminNotifications.Where(n=>n.RecipientId==uid && n.Kind=="Review" && n.EventKey.StartsWith("review:"+id+":") && n.ReadAt==null)
            .ExecuteUpdateAsync(s=>s.SetProperty(n=>n.ReadAt,DateTime.UtcNow),ct);
        return ReviewReturn(returnUrl,id);
    }
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> PhanHoiDanhGia([FromRoute]int id,ReviewReplyInput input,CancellationToken ct)
    {
        input.Content=input.Content?.Trim()??"";
        if(!ModelState.IsValid || id<=0 || input.Version<0 || input.Version==long.MaxValue || input.Content.Length is <3 or >1500)
            return BadRequest(new {message="Phản hồi cần từ 3 đến 1500 ký tự và phiên bản hợp lệ. Vui lòng kiểm tra lại."});
        var now=DateTime.UtcNow;
        var changed=await Db.ProductReviews.Where(r=>r.Id==id && r.IsCurrent && r.Version==input.Version)
            .ExecuteUpdateAsync(s=>s.SetProperty(r=>r.ReplyContent,input.Content)
                .SetProperty(r=>r.ReplyAdminId,ShoppingIdentity.UserId(User))
                .SetProperty(r=>r.ReplyCreatedAt,r=>r.ReplyCreatedAt??now)
                .SetProperty(r=>r.ReplyUpdatedAt,now).SetProperty(r=>r.Version,r=>r.Version+1),ct);
        if(changed==0) {
            if(!await Db.ProductReviews.AnyAsync(r=>r.Id==id,ct))return NotFound(new {message="Không tìm thấy đánh giá."});
            return Conflict(new {message="Đánh giá vừa thay đổi hoặc đã là bản lưu cũ. Vui lòng tải lại trang trước khi phản hồi."});
        }
        if(Request.Headers["X-Requested-With"]=="XMLHttpRequest")
            return Json(new {message="Đã lưu phản hồi từ GreenShop.",version=input.Version+1,content=input.Content,updatedAt=now});
        TempData["SuccessMessage"]="Đã lưu phản hồi từ GreenShop.";
        return RedirectToAction(nameof(DanhGia),new{reviewId=id});
    }
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> AnHienDanhGia([FromRoute]int id,[FromForm,BindRequired]long version,[FromForm,BindRequired]bool hidden,string? returnUrl,CancellationToken ct)
    {
        if(!ModelState.IsValid || id<=0 || version<0 || version==long.MaxValue) return BadRequest(new {message="Thông tin cập nhật không hợp lệ. Vui lòng tải lại trang."});
        var changed=await Db.ProductReviews.Where(r=>r.Id==id && r.Version==version).ExecuteUpdateAsync(s=>s.SetProperty(r=>r.IsHidden,hidden).SetProperty(r=>r.Version,r=>r.Version+1),ct);
        if(changed==0) return Conflict(new {message="Dữ liệu vừa thay đổi. Vui lòng tải lại trang và kiểm tra người phụ trách."});return ReviewReturn(returnUrl,id);
    }
    private IActionResult ReviewReturn(string? returnUrl,int id) => Url.IsLocalUrl(returnUrl) && returnUrl!.Split('?')[0]=="/Admin/KhachHang/DanhGia"
        ? LocalRedirect(returnUrl) : RedirectToAction(nameof(DanhGia),new{reviewId=id});
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> MoLai([FromRoute]int id,[FromForm,BindRequired]long version,CancellationToken ct)
    {
        if(!ModelState.IsValid || id<=0 || version<0 || version==long.MaxValue)return BadRequest();
        var uid=ShoppingIdentity.UserId(User);
        var changed=await Db.ShopConversations.Where(c=>c.Id==id && c.Version==version && c.Status=="Resolved" && c.AssignedAdminId==uid)
            .ExecuteUpdateAsync(s=>s.SetProperty(c=>c.Status,"InProgress").SetProperty(c=>c.Version,c=>c.Version+1),ct);
        if(changed==0)return Conflict(new{message="Cuộc trò chuyện vừa thay đổi hoặc do quản trị viên khác phụ trách. Vui lòng tải lại."});
        return RedirectToAction(nameof(TroChuyen),new{id});
    }
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> TiepNhan([FromRoute]int id,[FromForm,BindRequired]long version,CancellationToken ct)
    {
        if(!ModelState.IsValid || id<=0 || version<0 || version==long.MaxValue) return BadRequest(new {message="Thông tin tiếp nhận không hợp lệ. Vui lòng tải lại trang."});
        var uid=ShoppingIdentity.UserId(User);
        var changed=await Db.ShopConversations.Where(c=>c.Id==id && c.Version==version && c.AssignedAdminId==null && c.Status=="Waiting")
            .ExecuteUpdateAsync(s=>s.SetProperty(c=>c.AssignedAdminId,uid).SetProperty(c=>c.Status,"InProgress").SetProperty(c=>c.Version,c=>c.Version+1),ct);
        if(changed==0) return Conflict(new {message="Dữ liệu vừa thay đổi. Vui lòng tải lại trang và kiểm tra người phụ trách."});return RedirectToAction(nameof(TroChuyen),new{id});
    }
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> KetThuc([FromRoute]int id,[FromForm,BindRequired]long version,CancellationToken ct)
    {
        if(!ModelState.IsValid || id<=0 || version<0 || version==long.MaxValue) return BadRequest(new {message="Thông tin kết thúc không hợp lệ. Vui lòng tải lại trang."});
        var uid=ShoppingIdentity.UserId(User);
        var changed=await Db.ShopConversations.Where(c=>c.Id==id && c.Version==version && c.AssignedAdminId==uid && c.Status=="InProgress")
            .ExecuteUpdateAsync(s=>s.SetProperty(c=>c.Status,"Resolved").SetProperty(c=>c.Version,c=>c.Version+1),ct);
        if(changed==0) return Conflict(new {message="Dữ liệu vừa thay đổi. Vui lòng tải lại trang và kiểm tra người phụ trách."});return RedirectToAction(nameof(TroChuyen),new{id});
    }
    [HttpGet] public async Task<IActionResult> ThongBaoCuaToi(int page=1,CancellationToken ct=default)
    {
        if(page<1 || page>100000) return BadRequest();Response.Headers.CacheControl="no-store";
        var uid=ShoppingIdentity.UserId(User);
        var rows=await Db.AdminNotifications.AsNoTracking().Where(n=>n.RecipientId==uid).OrderByDescending(n=>n.Id).Skip((page-1)*30).Take(31).ToListAsync(ct);
        ViewData["Page"]=page;ViewData["HasNext"]=rows.Count>30;return View(rows.Take(30).ToList());
    }
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> DocThongBao([FromRoute]long id,CancellationToken ct)
    {
        var uid=ShoppingIdentity.UserId(User);
        var notice=await Db.AdminNotifications.AsNoTracking().FirstOrDefaultAsync(n=>n.Id==id && n.RecipientId==uid,ct);
        if(notice==null) return NotFound();
        await Db.AdminNotifications.Where(n=>n.Id==id && n.RecipientId==uid && n.ReadAt==null).ExecuteUpdateAsync(s=>s.SetProperty(n=>n.ReadAt,DateTime.UtcNow),ct);
        return LocalRedirect(notice.Link);
    }
    [HttpPost,ValidateAntiForgeryToken] public async Task<IActionResult> DocTatCa(CancellationToken ct)
    {
        var uid=ShoppingIdentity.UserId(User);
        await Db.AdminNotifications.Where(n=>n.RecipientId==uid && n.ReadAt==null).ExecuteUpdateAsync(s=>s.SetProperty(n=>n.ReadAt,DateTime.UtcNow),ct);
        return RedirectToAction(nameof(ThongBaoCuaToi));
    }
}
