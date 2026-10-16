using System.Data;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public enum AdminOrderOperation { Transition, Cancel, Note, CollectCod, VerifyInventory, CollectBankTransfer }
public record OrderMutationResult(int StatusCode, string Message);

public class AdminOrderService(AppDbContext db)
{
    public Task<OrderMutationResult> ExecuteAsync(int id, int adminId, AdminOrderCommand command,
        AdminOrderOperation operation, OrderStatus? target, CancellationToken ct, long adminSessionVersion = 0) =>
        db.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
        {
            db.ChangeTracker.Clear();
            await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
            var actor = await ShoppingIdentity.LockUserAsync(db,adminId,ct);
            if (actor == null || actor.Role!=UserRole.Admin || !actor.IsActive || actor.SessionVersion!=adminSessionVersion) return new OrderMutationResult(403, "Tài khoản không có quyền quản trị hợp lệ.");
            var order = await db.Orders.AsNoTracking().Include(o => o.Items).FirstOrDefaultAsync(o => o.Id == id, ct);
            if (order == null) return new OrderMutationResult(404, "Không tìm thấy đơn hàng.");
            if (order.Version != command.ExpectedVersion || order.Version == long.MaxValue)
                return new OrderMutationResult(409, "Đơn hàng đã thay đổi. Dữ liệu mới đã được tải; hãy kiểm tra trước khi thao tác lại.");
            var note = command.Note?.Trim() ?? string.Empty;
            var versioned = db.Orders.Where(o => o.Id == id && o.Version == command.ExpectedVersion && o.Status == order.Status);
            int changed;
            var kind = OrderHistoryKind.Status;
            OrderStatus? next = null;
            if (operation is AdminOrderOperation.Transition or AdminOrderOperation.Cancel or AdminOrderOperation.VerifyInventory or AdminOrderOperation.CollectCod or AdminOrderOperation.CollectBankTransfer)
            {
                if (!PaymentMethods.ValidMoney(order))
                    return new OrderMutationResult(422, "Chi tiết và tổng tiền không khớp. Cần đối chiếu đơn hàng; hệ thống không tự sửa giá lịch sử.");
            }
            switch (operation)
            {
                case AdminOrderOperation.Transition:
                    if (!target.HasValue || OrderWorkflow.Next(order.Status) != target.Value)
                        return new OrderMutationResult(409, "Không thể chuyển trạng thái này. Chỉ được chuyển tới bước kế tiếp của đơn hàng.");
                    if (order.InventoryStatus != OrderInventoryStatus.Deducted)
                        return new OrderMutationResult(422, "Cần đối chiếu và xác nhận đơn cũ đã trừ kho trước khi xử lý.");
                    if(order.PaymentMethod==PaymentMethods.VietQr && !order.IsPaid && target is OrderStatus.Shipping or OrderStatus.Completed)
                        return new OrderMutationResult(422,"Đơn VietQR chưa được xác nhận nhận tiền. Cần đối chiếu và xác nhận thanh toán trước khi giao hàng.");
                    next = target.Value;
                    changed = await versioned.ExecuteUpdateAsync(s => s.SetProperty(o => o.Status, target.Value)
                        .SetProperty(o => o.Version, o => o.Version + 1), ct);
                    break;
                case AdminOrderOperation.Cancel:
                    if (!OrderWorkflow.CanCancel(order.Status))
                        return new OrderMutationResult(409, "Chỉ được hủy đơn chờ xác nhận, đã xác nhận hoặc đang xử lý. Đơn đang giao/đã giao cần quy trình khác.");
                    if (order.IsPaid) return new OrderMutationResult(422, "Đơn đã thanh toán cần đối chiếu hoàn tiền; không thể hủy bằng thao tác thông thường.");
                    if (order.InventoryStatus != OrderInventoryStatus.Deducted)
                        return new OrderMutationResult(422, "Chưa có căn cứ trừ kho cho đơn cũ. Hãy đối chiếu trước khi hủy; chưa hoàn kho.");
                    if (string.IsNullOrWhiteSpace(note)) return new OrderMutationResult(422, "Vui lòng nhập lý do hủy đơn.");
                    if (order.Items.Any(i => !i.ProductId.HasValue))
                        return new OrderMutationResult(422, "Sản phẩm trong đơn đã bị xóa. Không thể tự hoàn kho; cần đối chiếu trước khi hủy.");
                    next = OrderStatus.Cancelled;
                    // Claim the order before touching products. The CAS winner alone restores stock.
                    changed = await versioned.ExecuteUpdateAsync(s => s.SetProperty(o => o.Status, OrderStatus.Cancelled)
                        .SetProperty(o => o.InventoryStatus, OrderInventoryStatus.Restored)
                        .SetProperty(o => o.Version, o => o.Version + 1), ct);
                    if (changed == 1)
                    {
                        foreach (var group in order.Items.GroupBy(i => i.ProductId!.Value).OrderBy(g => g.Key))
                        {
                            var quantity = group.Sum(i => (long)i.Quantity);
                            if (quantity > int.MaxValue) return new OrderMutationResult(422, "Số lượng hoàn kho vượt giới hạn. Toàn bộ thao tác đã được hủy.");
                            var restored = await db.Products.Where(p => p.Id == group.Key && p.StockQuantity >= 0 && p.StockQuantity <= int.MaxValue - quantity)
                                .ExecuteUpdateAsync(s => s.SetProperty(p => p.StockQuantity, p => p.StockQuantity + (int)quantity), ct);
                            if (restored != 1) return new OrderMutationResult(422, "Không thể hoàn kho vì sản phẩm không còn tồn tại hoặc tồn kho vượt giới hạn. Đơn chưa bị hủy.");
                        }
                    }
                    break;
                case AdminOrderOperation.Note:
                    if (note == order.AdminNote) return new OrderMutationResult(200, "Ghi chú không thay đổi.");
                    kind = OrderHistoryKind.Note;
                    changed = await versioned.ExecuteUpdateAsync(s => s.SetProperty(o => o.AdminNote, note)
                        .SetProperty(o => o.Version, o => o.Version + 1), ct);
                    break;
                case AdminOrderOperation.CollectCod:
                    if (order.Status != OrderStatus.Completed || order.IsPaid || !string.Equals(order.PaymentMethod, "COD", StringComparison.OrdinalIgnoreCase))
                        return new OrderMutationResult(409, "Chỉ xác nhận thu COD cho đơn đã giao và chưa thanh toán. Trạng thái giao hàng không chứng minh đã thu tiền.");
                    if (string.IsNullOrWhiteSpace(note)) return new OrderMutationResult(422, "Vui lòng nhập căn cứ đối chiếu tiền COD đã thu.");
                    kind = OrderHistoryKind.Payment;
                    changed = await versioned.Where(o => !o.IsPaid).ExecuteUpdateAsync(s => s.SetProperty(o => o.IsPaid, true)
                        .SetProperty(o=>o.PaidAt,DateTime.UtcNow).SetProperty(o=>o.PaymentConfirmedById,actor.Id).SetProperty(o=>o.PaymentConfirmedByName,actor.FullName)
                        .SetProperty(o => o.Version, o => o.Version + 1), ct);
                    break;
                case AdminOrderOperation.CollectBankTransfer:
                    if(order.Status==OrderStatus.Cancelled || order.IsPaid || order.PaymentMethod!=PaymentMethods.VietQr)
                        return new OrderMutationResult(409,"Chỉ xác nhận nhận tiền cho đơn VietQR chưa thanh toán và chưa hủy.");
                    if(!VietQrImages.AccountValid(order.BankBinSnapshot,order.BankAccountSnapshot,order.BankHolderSnapshot) || string.IsNullOrEmpty(order.TransferContent))
                        return new OrderMutationResult(422,"Thông tin chuyển khoản lịch sử chưa đủ. Cần đối chiếu thủ công.");
                    if(string.IsNullOrWhiteSpace(note)) return new OrderMutationResult(422,"Vui lòng nhập căn cứ hoặc mã giao dịch đã đối chiếu.");
                    kind=OrderHistoryKind.Payment;
                    changed=await versioned.Where(o=>!o.IsPaid).ExecuteUpdateAsync(s=>s.SetProperty(o=>o.IsPaid,true)
                        .SetProperty(o=>o.PaidAt,DateTime.UtcNow).SetProperty(o=>o.PaymentConfirmedById,actor.Id).SetProperty(o=>o.PaymentConfirmedByName,actor.FullName)
                        .SetProperty(o=>o.Version,o=>o.Version+1),ct);
                    break;
                case AdminOrderOperation.VerifyInventory:
                    if (order.InventoryStatus != OrderInventoryStatus.Unverified || !OrderWorkflow.CanCancel(order.Status))
                        return new OrderMutationResult(409, "Chỉ đối chiếu trừ kho cho đơn cũ chưa xác minh và chưa giao/hủy.");
                    if (string.IsNullOrWhiteSpace(note)) return new OrderMutationResult(422, "Vui lòng ghi căn cứ xác nhận đã trừ kho.");
                    kind = OrderHistoryKind.Inventory;
                    changed = await versioned.ExecuteUpdateAsync(s => s.SetProperty(o => o.InventoryStatus, OrderInventoryStatus.Deducted)
                        .SetProperty(o => o.Version, o => o.Version + 1), ct);
                    break;
                default: return new OrderMutationResult(400, "Thao tác không hợp lệ.");
            }
            if (changed != 1) return new OrderMutationResult(409, "Một quản trị viên khác vừa cập nhật đơn. Dữ liệu mới đã được tải; không có thao tác lặp.");
            db.OrderStatusHistories.Add(new OrderStatusHistory
            {
                OrderId = id, Kind = kind, FromStatus = next.HasValue ? order.Status : null, ToStatus = next,
                CreatedAt = DateTime.UtcNow, AdminId = actor.Id, AdminName = actor.FullName, Note = note
            });
            await db.SaveChangesAsync(ct);
            await transaction.CommitAsync(ct);
            return new OrderMutationResult(200, operation switch
            {
                AdminOrderOperation.Cancel => "Đã hủy đơn và hoàn kho đúng một lần.",
                AdminOrderOperation.Note => "Đã lưu ghi chú quản trị.",
                AdminOrderOperation.CollectCod => "Đã ghi nhận xác nhận thu COD và căn cứ đối chiếu.",
                AdminOrderOperation.CollectBankTransfer => "Đã ghi nhận đã nhận tiền chuyển khoản. Trạng thái giao hàng và tồn kho được giữ nguyên.",
                AdminOrderOperation.VerifyInventory => "Đã ghi nhận đối chiếu trừ kho. Không thay đổi số lượng tồn kho.",
                _ => $"Đã cập nhật: {OrderWorkflow.Label(next!.Value)}. Trạng thái thanh toán được giữ nguyên."
            });
        });
}
