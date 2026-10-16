using System.Security.Claims;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using BCryptNet = BCrypt.Net.BCrypt;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.RateLimiting;
using MySqlConnector;

namespace GreenShop.Web.Controllers
{
    [RequestSizeLimit(32*1024)]
    [RequestFormLimits(ValueLengthLimit=2048,ValueCountLimit=16)]
    public class AccountController : Controller
    {
        private readonly AppDbContext _context;

        private readonly Observability _observability;

        public AccountController(AppDbContext context, Observability observability)
        {
            _context = context;
            _observability = observability;
        }

        #region 1. ĐĂNG KÝ (REGISTER)

        [HttpGet]
        public IActionResult Register(string? returnUrl = null)
        {
            returnUrl = ShoppingIdentity.SafeReturnUrl(returnUrl);
            ViewData["ReturnUrl"] = returnUrl;
            if (User.Identity != null && User.Identity.IsAuthenticated)
            {
                if (returnUrl != null) return LocalRedirect(returnUrl);
                return RedirectToUserRolePage();
            }
            return View();
        }

        [HttpPost]
        [EnableRateLimiting("account")]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Register(RegisterViewModel model, string? returnUrl = null)
        {
            returnUrl = ShoppingIdentity.SafeReturnUrl(returnUrl);
            ViewData["ReturnUrl"] = returnUrl;
            if(System.Text.Encoding.UTF8.GetByteCount(model.Password??"")>72)
                ModelState.AddModelError(nameof(model.Password),"Mật khẩu quá dài. Vui lòng chọn mật khẩu ngắn hơn để các ký tự đều được bảo vệ.");
            if (!ModelState.IsValid) return View(model);
            model.Email=model.Email.Trim().ToLowerInvariant();
            if(ShopOwnership.IsOwnerEmail(model.Email)) {
                ModelState.AddModelError("Email","Email này dành cho tài khoản chủ shop và không thể đăng ký công khai.");
                return View(model);
            }

            if (await _context.Users.AnyAsync(u => u.Email.ToLower() == model.Email.ToLower()))
            {
                ModelState.AddModelError("Email", "Email này đã được đăng ký sử dụng.");
                return View(model);
            }

            string hashedPassword = BCryptNet.HashPassword(model.Password);

            var newUser = new User
            {
                FullName = model.FullName,
                Email = model.Email.ToLower().Trim(),
                Phone = model.Phone ?? string.Empty,
                PasswordHash = hashedPassword,
                Role = UserRole.Customer,
                CreatedAt = DateTime.UtcNow
            };

            _context.Users.Add(newUser);
            try{await _context.SaveChangesAsync();}
            catch(DbUpdateException ex) when(ex.InnerException is MySqlException {Number:1062})
            {
                ModelState.AddModelError("Email","Email này đã được đăng ký sử dụng.");
                return View(model);
            }

            TempData["RegisteredEmail"] = newUser.Email;
            TempData["SuccessMessage"] = "Đăng ký tài khoản thành công! Vui lòng đăng nhập.";
            return RedirectToRoute(PortalAuthentication.CustomerLoginRoute, new { returnUrl });
        }

        #endregion

        #region 2. ĐĂNG NHẬP (LOGIN)

        [HttpGet("/Account/Login", Name=PortalAuthentication.CustomerLoginRoute)]
        [HttpGet("/Admin/Account/Login", Name=PortalAuthentication.AdminLoginRoute, Order=1)]
        public IActionResult Login(string? returnUrl = null)
        {
            var adminPortal=PortalAuthentication.IsAdmin(Request);
            ViewData["AdminPortal"]=adminPortal;
            returnUrl = PortalAuthentication.SafeReturnUrl(returnUrl,adminPortal);
            if (User.Identity != null && User.Identity.IsAuthenticated)
            {
                if (returnUrl != null) return LocalRedirect(returnUrl);
                return RedirectToUserRolePage();
            }

            ViewData["ReturnUrl"] = returnUrl;
            var registeredEmail = TempData["RegisteredEmail"] as string;
            ViewBag.RegisteredEmail = registeredEmail;
            return View(new LoginViewModel
            {
                Email = registeredEmail ?? string.Empty
            });
        }

        [HttpPost("/Account/Login")]
        [HttpPost("/Admin/Account/Login", Order=1)]
        [EnableRateLimiting("account")]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Login(LoginViewModel model, string? returnUrl = null)
        {
            var adminPortal=PortalAuthentication.IsAdmin(Request);
            ViewData["AdminPortal"]=adminPortal;
            returnUrl = PortalAuthentication.SafeReturnUrl(returnUrl,adminPortal);
            ViewData["ReturnUrl"] = returnUrl;

            if (!ModelState.IsValid) return View(model);

            var user = await _context.Users.FirstOrDefaultAsync(u => u.Email.ToLower() == model.Email.ToLower());

            if (user == null || !BCryptNet.Verify(model.Password, user.PasswordHash))
            {
                _observability.LoginFailed(HttpContext);
                ModelState.AddModelError(string.Empty, "Email hoặc mật khẩu không chính xác.");
                return View(model);
            }

            if (!user.IsActive)
            {
                ModelState.AddModelError(string.Empty, "Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên để được hỗ trợ.");
                return View(model);
            }

            if(adminPortal && user.Role!=UserRole.Admin)
            {
                _observability.AccessDenied(HttpContext, "portal_role_mismatch");
                ModelState.AddModelError(string.Empty,"Tài khoản này không có quyền quản trị. Vui lòng đăng nhập ở trang khách hàng.");
                return View(model);
            }

            string? assignedRole = user.Role switch
            {
                UserRole.Customer => "Customer",
                UserRole.Admin => "Admin",
                _ => null
            };

            if (assignedRole == null)
            {
                ModelState.AddModelError(string.Empty, "Tài khoản chưa được cấu hình quyền hợp lệ.");
                return View(model);
            }

            bool isAdmin = user.Role == UserRole.Admin;

            // Sử dụng định danh chuẩn của .NET để hệ thống tự nhận diện Role
            var claims = new List<Claim>
            {
                new Claim(ClaimTypes.NameIdentifier, user.Id.ToString()),
                new Claim(ClaimTypes.Name, user.FullName),
                new Claim(ClaimTypes.Email, user.Email),
                new Claim(ClaimTypes.Role, assignedRole),
                new Claim(UserSession.VersionClaim, user.SessionVersion.ToString(System.Globalization.CultureInfo.InvariantCulture))
            };

            var claimsIdentity = new ClaimsIdentity(
                claims,
                CookieAuthenticationDefaults.AuthenticationScheme,
                ClaimTypes.Name,
                ClaimTypes.Role);
            var authProperties = new AuthenticationProperties
            {
                IsPersistent = model.RememberMe,
                ExpiresUtc = DateTimeOffset.UtcNow.AddDays(7)
            };

            await HttpContext.SignInAsync(
                isAdmin ? PortalAuthentication.AdminScheme : PortalAuthentication.CustomerScheme,
                new ClaimsPrincipal(claimsIdentity),
                authProperties);

            _observability.LoginSucceeded(HttpContext);

            if (returnUrl != null && (!isAdmin || adminPortal)) return LocalRedirect(returnUrl);

            if (isAdmin)
            {
                return RedirectToAction("Index", "Admin", new { area = "Admin" });
            }

            return RedirectToAction("Index", "Home");
        }

        #endregion

        #region 3. ĐĂNG XUẤT & ACCESS DENIED

        [HttpPost("/Account/Logout", Name=PortalAuthentication.CustomerLogoutRoute)]
        [HttpPost("/Admin/Account/Logout", Name=PortalAuthentication.AdminLogoutRoute, Order=1)]
        [ValidateAntiForgeryToken]
        [Authorize]
        public async Task<IActionResult> Logout()
        {
            await HttpContext.SignOutAsync(PortalAuthentication.Scheme(Request));
            return RedirectToRoute(PortalAuthentication.IsAdmin(Request) ? PortalAuthentication.AdminLoginRoute : PortalAuthentication.CustomerLoginRoute);
        }

        [HttpGet("/Account/AccessDenied")]
        [HttpGet("/Admin/Account/AccessDenied", Order=1)]
        public IActionResult AccessDenied()
        {
            return View();
        }

        #endregion

        #region HELPER METHODS

        private IActionResult RedirectToUserRolePage()
        {
            if (User.IsInRole("Admin"))
            {
                return RedirectToAction("Index", "Admin", new { area = "Admin" });
            }
            return RedirectToAction("Index", "Home");
        }

        #endregion
    }
}
