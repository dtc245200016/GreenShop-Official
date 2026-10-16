using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Controllers;

[Authorize(Roles="Customer")]
public class TuongTacController(AppDbContext db,IWebHostEnvironment environment,ILogger<TuongTacController> logger) : ChatControllerBase(db)
{
    [HttpGet,AllowAnonymous] public IActionResult TroChuyen()=>RedirectToAction("Index","Home",new{chat="shop",portal=User.IsInRole("Admin")?"admin":null});
    [HttpGet] public Task<IActionResult> TinNhanMoi(long after=0,CancellationToken ct=default)=>MessagesAsync(0,false,after,ct);
    [HttpPost,ValidateAntiForgeryToken] public Task<IActionResult> GuiTinNhan(MessageInput input,CancellationToken ct)=>SendAsync(0,false,input,ct);
    [HttpPost,ValidateAntiForgeryToken] public Task<IActionResult> DaDoc(long through,CancellationToken ct)=>ReadAsync(0,false,through,ct);

    private Task<OrderItem?> PurchasedAsync(int id,CancellationToken ct)=>Db.OrderItems.AsNoTracking().Include(i=>i.Order)
        .FirstOrDefaultAsync(i=>i.Id==id && i.Order.UserId==ShoppingIdentity.UserId(User) && i.Order.Status==OrderStatus.Completed && i.ProductId!=null,ct);

    [HttpGet] public async Task<IActionResult> DanhGia([FromRoute]int id,CancellationToken ct)
    {
        var item=await PurchasedAsync(id,ct);if(item==null) return NotFound();
        var existing=await Db.ProductReviews.AsNoTracking().FirstOrDefaultAsync(r=>r.UserId==ShoppingIdentity.UserId(User) && r.OrderItem.OrderId==item.OrderId && r.ProductId==item.ProductId && r.IsCurrent,ct);
        return View(new ReviewInput{OrderId=item.OrderId,OrderItemId=id,ProductName=item.ProductName,Editing=existing!=null,ReviewId=existing?.Id??0,Version=existing?.Version??0,Stars=existing?.Stars??0,Content=existing?.Content??""});
    }
    [HttpPost,ValidateAntiForgeryToken,RequestSizeLimit(6*1024*1024)]
    public async Task<IActionResult> DanhGia([FromRoute]int id,ReviewInput input,CancellationToken ct)
    {
        var item=await PurchasedAsync(id,ct);if(item==null) return NotFound();
        input.OrderId=item.OrderId;input.OrderItemId=id;input.ProductName=item.ProductName;input.Editing=input.ReviewId>0;input.Content=input.Content?.Trim()??"";
        if(input.Content.Length<3) ModelState.AddModelError(nameof(input.Content),"Nhận xét cần ít nhất 3 ký tự.");
        var storage=new ProductImageStorage(environment,logger);
        if(input.Photos.Count>5 || input.Photos.Sum(f=>f.Length)>5*1024*1024) ModelState.AddModelError(nameof(input.Photos),"Tối đa 5 ảnh, tổng dung lượng không quá 5 MiB.");
        foreach(var photo in input.Photos.Take(5)) {
            var error=photo.Length>2*1024*1024?"Mỗi ảnh tối đa 2 MiB.":await storage.ValidateAsync(photo,ct);
            if(error!=null) ModelState.AddModelError(nameof(input.Photos),error);
        }
        if(!ModelState.IsValid) {Response.StatusCode=400;return View(input);}
        var urls=new List<string>();var kept=false;
        try {
            foreach(var photo in input.Photos) urls.Add(await storage.SaveAsync(photo,ct));
            var result=await Db.Database.CreateExecutionStrategy().ExecuteAsync(async()=> {
                Db.ChangeTracker.Clear();await using var tx=await Db.Database.BeginTransactionAsync(ct);
                var actor=await ShoppingIdentity.LockUserAsync(Db,ShoppingIdentity.UserId(User),ct);
                if(actor==null || actor.Role!=UserRole.Customer || !actor.IsActive || actor.SessionVersion!=UserSession.Version(User)) return 403;
                if(await PurchasedAsync(id,ct)==null) return 404;
                var existing=await Db.ProductReviews.FirstOrDefaultAsync(r=>r.UserId==actor.Id && r.OrderItem.OrderId==item.OrderId && r.ProductId==item.ProductId && r.IsCurrent,ct);
                if(existing!=null && (input.ReviewId!=existing.Id || input.Version!=existing.Version)) return 409;
                if(existing==null && input.ReviewId!=0) return 409;
                var review=existing??new ProductReview{OrderItemId=id,UserId=actor.Id,ProductId=item.ProductId,ProductName=item.ProductName,CreatedAt=DateTime.UtcNow};
                if(existing!=null && urls.Count==0 && review.Content==input.Content && review.Stars==input.Stars) {await tx.CommitAsync(ct);return 200;}
                review.Stars=input.Stars;review.Content=input.Content;
                if(urls.Count>0) {
                    review.Image1=urls.ElementAtOrDefault(0);review.Image2=urls.ElementAtOrDefault(1);review.Image3=urls.ElementAtOrDefault(2);review.Image4=urls.ElementAtOrDefault(3);review.Image5=urls.ElementAtOrDefault(4);
                }
                if(existing==null) Db.ProductReviews.Add(review);
                else {review.UpdatedAt=DateTime.UtcNow;review.Version++;}
                await Db.SaveChangesAsync(ct);
                await AdminNotifications.AddAsync(Db,$"review:{review.Id}:{review.Version}","Review",existing==null?"Đánh giá mới":"Đánh giá vừa cập nhật","/Admin/KhachHang/DanhGia?reviewId="+review.Id,ct);
                await tx.CommitAsync(ct);return 200;
            });
            if(result==403) return Forbid();if(result==404) return NotFound();
            kept=result==200;TempData[result==200?"SuccessMessage":"WarningMessage"]=result==200?"Cảm ơn bạn! Đánh giá đã được lưu.":"Đánh giá đã thay đổi. Vui lòng mở lại biểu mẫu để chỉnh sửa.";
            return RedirectToAction("ChiTietDonHang","ThanhToan",new{id=item.OrderId});
        } catch(Exception ex) when(ex is DbUpdateException or IOException or UnauthorizedAccessException) {
            logger.LogWarning("Chưa thể lưu đánh giá hoặc ảnh đính kèm.");ModelState.AddModelError("","Chưa thể lưu đánh giá. Vui lòng thử lại.");Response.StatusCode=503;return View(input);
        } finally {
            if(!kept && urls.Count>0) {
                // A cancelled response or transient commit error may still have committed.
                // Never remove an image referenced by the persisted review.
                using var cleanupTimeout=new CancellationTokenSource(TimeSpan.FromSeconds(3));
                try {
                    var committed=await Db.ProductReviews.AsNoTracking().FirstOrDefaultAsync(r=>r.UserId==ShoppingIdentity.UserId(User) && r.OrderItem.OrderId==item.OrderId && r.ProductId==item.ProductId && r.IsCurrent,cleanupTimeout.Token);
                    var referenced=new[]{committed?.Image1,committed?.Image2,committed?.Image3,committed?.Image4,committed?.Image5};
                    foreach(var url in urls.Where(u=>!referenced.Contains(u))) storage.Delete(url);
                } catch(Exception ex) when(ex is System.Data.Common.DbException or Microsoft.EntityFrameworkCore.Storage.RetryLimitExceededException or OperationCanceledException) {
                    logger.LogWarning("Giữ ảnh đính kèm vì chưa thể xác minh kết quả lưu đánh giá.");
                }
            }
        }
    }
}
