using System.Data;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public enum AdminUserOperation { Profile, Role, Lock, Unlock }
public record UserMutationResult(int StatusCode, string Message);

public class AdminUserService(AppDbContext db)
{
    public Task<UserMutationResult> ExecuteAsync(int id, int actorId, long actorSessionVersion, AdminUserCommand command,
        AdminUserOperation operation, CancellationToken ct) => db.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
    {
        db.ChangeTracker.Clear();
        await using var transaction = await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted, ct);
        // Current locking reads serialize admin membership changes across all app instances.
        // Recheck the actor after waiting: a concurrently demoted/locked actor cannot finish a queued request.
        var administrators = await db.Users.FromSqlRaw("SELECT * FROM Users WHERE Role = 1 AND IsActive = 1 ORDER BY Id FOR UPDATE")
            .AsNoTracking().ToListAsync(ct);
        if (!administrators.Any(u => u.Id == actorId && u.SessionVersion == actorSessionVersion))
            return new UserMutationResult(403,"Quyền quản trị của phiên này không còn hiệu lực. Vui lòng đăng nhập lại.");
        var actor=administrators.Single(u=>u.Id==actorId);
        var owner=ShopOwnership.IsOwnerEmail(actor.Email);
        if(operation==AdminUserOperation.Role && !owner)
            return new UserMutationResult(403,"Chỉ chủ shop mới được thay đổi quyền tài khoản.");
        var account = await ShoppingIdentity.LockUserAsync(db,id,ct);
        if (account == null) return new UserMutationResult(404,"Không tìm thấy tài khoản.");
        if(!owner && (ShopOwnership.IsOwnerEmail(account.Email) || account.Role==UserRole.Admin && account.Id!=actorId))
            return new UserMutationResult(403,"Bạn không được thay đổi tài khoản chủ shop hoặc quản trị viên khác.");
        if (account.Version != command.ExpectedVersion || account.Version == long.MaxValue || account.SessionVersion == long.MaxValue)
            return new UserMutationResult(409,"Tài khoản vừa được cập nhật. Hãy kiểm tra thông tin mới trước khi thao tác lại.");
        var query = db.Users.Where(u => u.Id == id && u.Version == command.ExpectedVersion);
        int changed;
        if (operation == AdminUserOperation.Profile && command is AdminUserProfile profile)
        {
            var name = profile.FullName.Trim();
            var phone = profile.Phone?.Trim() ?? "";
            if (string.IsNullOrWhiteSpace(name)) return new UserMutationResult(422,"Họ tên không được để trống.");
            changed = await query.ExecuteUpdateAsync(s => s.SetProperty(u => u.FullName,name).SetProperty(u => u.Phone,phone)
                .SetProperty(u => u.Version,u => u.Version+1),ct);
        }
        else
        {
            var role = operation == AdminUserOperation.Role && command is AdminUserRoleCommand roleCommand ? roleCommand.TargetRole : account.Role;
            var active = operation switch { AdminUserOperation.Lock => false, AdminUserOperation.Unlock => true, _ => account.IsActive };
            if (!Enum.IsDefined(role)) return new UserMutationResult(400,"Vai trò không hợp lệ.");
            if (id == actorId && (!active || role != UserRole.Admin))
                return new UserMutationResult(422,"Bạn không thể tự khóa hoặc tự hạ quyền tài khoản đang đăng nhập.");
            if (account.Role == UserRole.Admin && account.IsActive && (!active || role != UserRole.Admin) && administrators.Count <= 1)
                return new UserMutationResult(422,"Cần giữ ít nhất một quản trị viên đang hoạt động. Hãy có quản trị viên khác trước khi thay đổi.");
            if (account.Role == role && account.IsActive == active) return new UserMutationResult(409,"Tài khoản đã ở vai trò hoặc trạng thái này. Không thực hiện thay đổi lặp.");
            changed = await query.ExecuteUpdateAsync(s => s.SetProperty(u => u.Role,role).SetProperty(u => u.IsActive,active)
                .SetProperty(u => u.Version,u => u.Version+1).SetProperty(u => u.SessionVersion,u => u.SessionVersion+1),ct);
        }
        if (changed != 1) return new UserMutationResult(409,"Một quản trị viên khác vừa cập nhật tài khoản. Thay đổi của bạn chưa được lưu.");
        await transaction.CommitAsync(ct);
        return new UserMutationResult(200,operation switch
        {
            AdminUserOperation.Profile => "Đã lưu thông tin người dùng.",
            AdminUserOperation.Role => "Đã đổi quyền. Người dùng cần đăng nhập lại để sử dụng quyền mới.",
            AdminUserOperation.Lock => "Đã khóa tài khoản và thu hồi các phiên đăng nhập. Đơn hàng và giỏ hàng được giữ nguyên.",
            _ => "Đã mở khóa tài khoản. Người dùng có thể đăng nhập lại với quyền hiện có."
        });
    });
}
