using System.Data;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public class CustomerTransfers(AppDbContext db)
{
    public Task<OrderMutationResult> NotifyAsync(int id,int userId,long version,long sessionVersion,CancellationToken ct) =>
        db.Database.CreateExecutionStrategy().ExecuteAsync(async()=>
    {
        await using var transaction=await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted,ct);
        var user=await ShoppingIdentity.LockUserAsync(db,userId,ct);
        if(user==null || !user.IsActive || user.SessionVersion!=sessionVersion) return new OrderMutationResult(403,"Phiên đăng nhập không còn hợp lệ.");
        var order=await db.Orders.AsNoTracking().FirstOrDefaultAsync(o=>o.Id==id && o.UserId==userId,ct);
        if(order==null) return new OrderMutationResult(404,"Không tìm thấy đơn hàng.");
        if(!PaymentMethods.NeedsTransfer(order)) return new OrderMutationResult(409,"Đơn hàng không còn cần thông báo chuyển khoản.");
        if(order.CustomerTransferNotifiedAt.HasValue) return new OrderMutationResult(200,"Đã ghi nhận thông báo. GreenShop đang kiểm tra giao dịch.");
        if(order.Version!=version || version==long.MaxValue) return new OrderMutationResult(409,"Đơn hàng đã thay đổi. Vui lòng tải lại trước khi thông báo.");
        var now=DateTime.UtcNow;
        var changed=await db.Orders.Where(o=>o.Id==id && o.UserId==userId && o.Version==version && !o.IsPaid && o.Status!=OrderStatus.Cancelled && o.CustomerTransferNotifiedAt==null)
            .ExecuteUpdateAsync(s=>s.SetProperty(o=>o.CustomerTransferNotifiedAt,now).SetProperty(o=>o.Version,o=>o.Version+1),ct);
        if(changed!=1) return new OrderMutationResult(409,"Đơn hàng vừa được cập nhật. Vui lòng tải lại.");
        db.OrderStatusHistories.Add(new OrderStatusHistory{OrderId=id,Kind=OrderHistoryKind.CustomerTransfer,CreatedAt=now,AdminName="",Note="Khách hàng đã thông báo chuyển khoản; chưa xác nhận nhận tiền."});
        await db.SaveChangesAsync(ct);await transaction.CommitAsync(ct);
        return new OrderMutationResult(200,"Đã ghi nhận thông báo. GreenShop sẽ kiểm tra giao dịch và xác nhận thanh toán.");
    });
}
