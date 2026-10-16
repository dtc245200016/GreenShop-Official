using System.Globalization;
using System.Security.Claims;
using System.Data.Common;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public class UserSession(AppDbContext db, Observability observability) : CookieAuthenticationEvents
{
    public const string VersionClaim = "GreenShop.SessionVersion";
    public const string UnavailableItem = "GreenShop.AuthenticationUnavailable";
    public static long Version(ClaimsPrincipal user) => long.TryParse(user.FindFirstValue(VersionClaim), NumberStyles.None,
        CultureInfo.InvariantCulture, out var version) && version >= 0 ? version : 0;

    public override async Task ValidatePrincipal(CookieValidatePrincipalContext context)
    {
        var principal = context.Principal;
        var id = principal == null ? 0 : ShoppingIdentity.UserId(principal);
        UserAccount? account;
        try
        {
            account = await db.Users.AsNoTracking().Where(u => u.Id == id)
                .Select(u => new UserAccount(u.IsActive,u.Role,u.SessionVersion,u.FullName,u.Email)).FirstOrDefaultAsync(context.HttpContext.RequestAborted);
        }
        catch (Exception ex) when (ex is DbException or Microsoft.EntityFrameworkCore.Storage.RetryLimitExceededException)
        {
            // Fail closed for this request, without destroying otherwise valid sessions during an outage.
            context.RejectPrincipal();
            context.HttpContext.Items[UnavailableItem] = true;
            return;
        }
        var raw = principal?.FindFirstValue(VersionClaim);
        // Cookies issued before this migration remain valid only while the account has never been revoked.
        var validVersion = raw == null ? account?.SessionVersion == 0
            : long.TryParse(raw, NumberStyles.None, CultureInfo.InvariantCulture, out var version) && version == account?.SessionVersion;
        if (account == null || !account.IsActive || !Enum.IsDefined(account.Role) || !validVersion
            || principal?.FindFirstValue(ClaimTypes.Role) != account.Role.ToString())
        {
            context.RejectPrincipal();
            await context.HttpContext.SignOutAsync(context.Scheme.Name);
            return;
        }
        if (principal!.Identity is ClaimsIdentity identity && (identity.Name != account.FullName || identity.FindFirst(ClaimTypes.Email)?.Value != account.Email))
        {
            var updated = new ClaimsIdentity(identity);
            foreach (var type in new[] { ClaimTypes.Name, ClaimTypes.Email })
                foreach (var claim in updated.FindAll(type).ToArray()) updated.RemoveClaim(claim);
            updated.AddClaim(new Claim(ClaimTypes.Name, account.FullName));
            updated.AddClaim(new Claim(ClaimTypes.Email, account.Email));
            context.ReplacePrincipal(new ClaimsPrincipal(updated));
            context.ShouldRenew = true;
        }
        if(context.Scheme.Name==PortalAuthentication.AdminScheme && account.Role==UserRole.Customer)
        {
            // Preserve old Customer sessions, while the original cookie becomes Admin-only.
            // An existing new Customer session takes precedence over any stale legacy cookie.
            if(!context.HttpContext.Request.Cookies.ContainsKey(PortalAuthentication.CustomerCookie))
            {
                await context.HttpContext.SignInAsync(PortalAuthentication.CustomerScheme,context.Principal!,context.Properties);
                context.HttpContext.Items[PortalAuthentication.MigratedCustomerItem]=context.Principal!;
            }
            context.RejectPrincipal();
            await context.HttpContext.SignOutAsync(context.Scheme.Name);
        }
        else if(context.Scheme.Name==PortalAuthentication.CustomerScheme && account.Role!=UserRole.Customer)
        {
            context.RejectPrincipal();
            await context.HttpContext.SignOutAsync(context.Scheme.Name);
        }
    }
    public override Task RedirectToAccessDenied(RedirectContext<CookieAuthenticationOptions> context)
    {
        observability.AccessDenied(context.HttpContext,"role_forbidden");
        return base.RedirectToAccessDenied(context);
    }
    private record UserAccount(bool IsActive, UserRole Role, long SessionVersion, string FullName, string Email);
}
