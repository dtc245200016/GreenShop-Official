using System.Data.Common;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Areas.Admin.Controllers;

[Area("Admin"), Authorize(Roles="Admin")]
public class NguoiDungController(AppDbContext db, ILogger<NguoiDungController> logger) : Controller
{
    [HttpGet]
    public async Task<IActionResult> QuanLyNguoiDung(AdminUserFilter filter, CancellationToken ct)
    {
        filter.Search = filter.Search?.Trim();
        if (!ModelState.IsValid || filter.Role.HasValue && !Enum.IsDefined(filter.Role.Value)
            || filter.Sort is not ("newest" or "oldest" or "name") || filter.PageSize is not (15 or 30 or 50)) return BadRequest();
        var stats = await db.Users.AsNoTracking().GroupBy(u => 1).Select(g => new {
            Total=g.Count(), Customers=g.Count(u => u.Role==UserRole.Customer), Administrators=g.Count(u => u.Role==UserRole.Admin),
            Active=g.Count(u=>u.IsActive), Locked=g.Count(u=>!u.IsActive)
        }).FirstOrDefaultAsync(ct);
        var query=db.Users.AsNoTracking();
        if (!string.IsNullOrEmpty(filter.Search)) query=query.Where(u=>u.FullName.Contains(filter.Search) || u.Email.Contains(filter.Search));
        if (filter.Role.HasValue) query=query.Where(u=>u.Role==filter.Role.Value);
        if (filter.Active.HasValue) query=query.Where(u=>u.IsActive==filter.Active.Value);
        var total=await query.CountAsync(ct);
        filter.Page=Math.Min(filter.Page,Math.Max(1,(int)Math.Ceiling(total/(double)filter.PageSize)));
        query=filter.Sort switch { "oldest"=>query.OrderBy(u=>u.CreatedAt).ThenBy(u=>u.Id),"name"=>query.OrderBy(u=>u.FullName).ThenBy(u=>u.Id),_=>query.OrderByDescending(u=>u.CreatedAt).ThenByDescending(u=>u.Id) };
        var rows=await Display(query.Skip((filter.Page-1)*filter.PageSize).Take(filter.PageSize)).ToListAsync(ct);
        return View(new AdminUserListViewModel { Filter=filter,Users=rows,MatchingCount=total,Total=stats?.Total??0,
            Customers=stats?.Customers??0,Administrators=stats?.Administrators??0,Active=stats?.Active??0,Locked=stats?.Locked??0 });
    }

    private IQueryable<AdminUserRow> Display(IQueryable<User> query) => query.Select(u=>new AdminUserRow {
        Id=u.Id,FullName=u.FullName,Email=u.Email,Phone=u.Phone,Role=u.Role,IsActive=u.IsActive,CreatedAt=u.CreatedAt,Version=u.Version,
        OrderCount=db.Orders.Count(o=>o.UserId==u.Id)
    });

    [HttpGet]
    public Task<IActionResult> ChiTietNguoiDung([FromRoute]int id,CancellationToken ct) => DetailAsync(id,ct);

    private async Task<IActionResult> DetailAsync(int id,CancellationToken ct,AdminUserProfile? submitted=null)
    {
        var account=await Display(db.Users.AsNoTracking().Where(u=>u.Id==id)).FirstOrDefaultAsync(ct);
        if (account==null) return NotFound();
        var activeAdmins=await db.Users.AsNoTracking().CountAsync(u=>u.IsActive && u.Role==UserRole.Admin,ct);
        var actorId=ShoppingIdentity.UserId(User);
        var owner=await db.Users.AsNoTracking().AnyAsync(u=>u.Id==actorId && u.IsActive && u.Role==UserRole.Admin && u.Email.ToLower()==ShopOwnership.OwnerEmail,ct);
        var self=id==actorId;var protectedOwner=ShopOwnership.IsOwnerEmail(account.Email);
        var last=account.IsActive && account.Role==UserRole.Admin && activeAdmins<=1;
        return View("ChiTietNguoiDung",new AdminUserDetailViewModel { Account=account,IsSelf=id==ShoppingIdentity.UserId(User),
            IsLastAdmin=last,SubmittedProfile=submitted,CanEditProfile=owner || !protectedOwner && (self || account.Role==UserRole.Customer),
            CanChangeRole=owner && !protectedOwner && !self && !last,CanChangeStatus=!self && !protectedOwner && !last && (owner || account.Role==UserRole.Customer) });
    }

    [HttpPost,ValidateAntiForgeryToken]
    public Task<IActionResult> CapNhatThongTinNguoiDung([FromRoute]int id,AdminUserProfile model,CancellationToken ct) => MutateAsync(id,model,AdminUserOperation.Profile,ct);
    [HttpPost,ValidateAntiForgeryToken]
    public Task<IActionResult> ThayDoiVaiTro([FromRoute]int id,AdminUserRoleCommand model,CancellationToken ct) => MutateAsync(id,model,AdminUserOperation.Role,ct);
    [HttpPost,ValidateAntiForgeryToken]
    public Task<IActionResult> KhoaTaiKhoan([FromRoute]int id,AdminUserCommand model,CancellationToken ct) => MutateAsync(id,model,AdminUserOperation.Lock,ct);
    [HttpPost,ValidateAntiForgeryToken]
    public Task<IActionResult> MoKhoaTaiKhoan([FromRoute]int id,AdminUserCommand model,CancellationToken ct) => MutateAsync(id,model,AdminUserOperation.Unlock,ct);

    private async Task<IActionResult> MutateAsync(int id,AdminUserCommand model,AdminUserOperation operation,CancellationToken ct)
    {
        if (id<=0) return NotFound();
        if (!ModelState.IsValid || model is AdminUserRoleCommand role && !Enum.IsDefined(role.TargetRole))
        {
            Response.StatusCode=400;
            ModelState.AddModelError("","Thông tin chưa hợp lệ. Kiểm tra họ tên, số điện thoại hoặc vai trò.");
            return await DetailAsync(id,ct,model as AdminUserProfile);
        }
        UserMutationResult result;
        try { result=await new AdminUserService(db).ExecuteAsync(id,ShoppingIdentity.UserId(User),UserSession.Version(User),model,operation,ct); }
        catch (Exception ex) when (ex is DbException or DbUpdateException)
        {
            logger.LogError(ex,"Không thể cập nhật tài khoản {UserId}.",id);
            result=new UserMutationResult(503,"Chưa thể lưu. Hãy tải lại thông tin tài khoản trước khi thử lại.");
        }
        if (result.StatusCode==404) return NotFound();
        if (result.StatusCode==403) return StatusCode(403,new{message=result.Message});
        if (result.StatusCode==200)
        {
            TempData["SuccessMessage"]=result.Message;
            return RedirectToAction(nameof(ChiTietNguoiDung),new {id});
        }
        Response.StatusCode=result.StatusCode;
        ModelState.AddModelError("",result.Message);
        return await DetailAsync(id,ct,operation==AdminUserOperation.Profile ? model as AdminUserProfile : null);
    }
}
