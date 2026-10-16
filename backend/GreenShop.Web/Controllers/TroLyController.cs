using System.ComponentModel.DataAnnotations;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using GreenShop.Web.Data;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.RateLimiting;

namespace GreenShop.Web.Controllers;

public class TroLyController(AppDbContext db,IAiChatProvider provider,AiConversationState history) : Controller
{
    public sealed class Input {
        [Required,StringLength(1000,MinimumLength=2)] public string Question { get; set; } = "";
        [StringLength(AiConversationState.MaximumTokenLength)] public string? Conversation {get;set;}
    }
    private string Binding()
    {
        const string cookie="GreenShop.AiBrowser";
        var browser=Request.Cookies[cookie];
        if(browser==null || !Regex.IsMatch(browser,@"\A[a-f0-9]{32}\z")) {
            browser=Convert.ToHexString(RandomNumberGenerator.GetBytes(16)).ToLowerInvariant();
            Response.Cookies.Append(cookie,browser,new CookieOptions {HttpOnly=true,Secure=Request.IsHttps,SameSite=SameSiteMode.Strict,IsEssential=true,MaxAge=TimeSpan.FromMinutes(30)});
        }
        return browser+":"+ShoppingIdentity.UserId(User)+":"+UserSession.Version(User);
    }
    [HttpGet] public IActionResult TrangThai() {
        Response.Headers.CacheControl="no-store";var binding=Binding();return Json(new {available=provider.Available,session=Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(binding))).ToLowerInvariant()});
    }
    [HttpPost,ValidateAntiForgeryToken,EnableRateLimiting("ai"),RequestSizeLimit(131072)]
    public async Task<IActionResult> Hoi(Input input,CancellationToken ct)
    {
        Response.Headers.CacheControl="no-store";
        if(!ModelState.IsValid) return BadRequest(new {message="Câu hỏi hoặc lịch sử vượt giới hạn."});
        var binding=Binding();var previous=history.Read(input.Conversation,binding);
        if(previous==null) return BadRequest(new {message="Hội thoại đã hết hạn hoặc không hợp lệ. Hãy bắt đầu cuộc trò chuyện mới.",resetConversation=true});
        if(!provider.Available) return StatusCode(503,new {message="Trợ lý AI chưa được cấu hình đầy đủ. Bạn có thể chat với cửa hàng."});
        var turns=previous.Append(new AiTurn("user",input.Question.Trim())).ToArray();
        // Public AI has no identity-dependent tools. Enforce these boundaries before contacting a model.
        var restricted=Regex.IsMatch(input.Question,@"(?i)(api.?key|credentials|connection.?string|mật khẩu|bí mật|đơn hàng|thanh toán|sửa giá|đổi giá|database|sql|/etc/|system prompt)");
        var unknownPolicy=Regex.IsMatch(input.Question,@"(?i)(khuyến mãi|giảm giá|đổi trả|hoàn tiền|bảo hành)");
        if(restricted || unknownPolicy) {
            var refusal=restricted?"Trợ lý chỉ tư vấn cây và thông tin công khai, không truy cập dữ liệu riêng tư hay thay đổi dữ liệu. Bạn có thể chat với cửa hàng để được hỗ trợ.":"Cửa hàng chưa cung cấp thông tin về chính sách hoặc chương trình bạn hỏi. Vui lòng chat với cửa hàng để xác nhận.";
            return Json(new {answer=refusal,products=Array.Empty<AiCatalogItem>(),conversation=history.Write(turns.Append(new AiTurn("assistant",refusal)).ToArray(),binding)});
        }
        var retrievalQuestion=input.Question;
        if(Regex.IsMatch(input.Question,@"(?i)(loại đó|cây đó|chúng|loại nào|còn loại|chăm sóc|tưới)") && previous.Count>0)
            retrievalQuestion=input.Question+" "+previous.Last(t=>t.Role=="user").Text;
        var context=await StoreCatalog.AiContextAsync(db,retrievalQuestion,ct);
        var reply=await provider.ReplyAsync(turns,context,ct);
        if(reply.Answer==null) {
            if(reply.Category=="quota") Response.Headers.RetryAfter="60";
            var message=reply.Category switch {
                "configuration"=>"Model AI chưa khả dụng hoặc cấu hình không hợp lệ. Vui lòng báo cửa hàng.",
                "authentication"=>"Kết nối AI chưa được cấp quyền hợp lệ. Vui lòng báo cửa hàng.",
                "quota"=>"Trợ lý AI đang hết hạn mức. Vui lòng đợi hoặc chat với cửa hàng.",
                "input_limit"=>"Cuộc trò chuyện đang quá dài. Hãy bắt đầu cuộc trò chuyện mới hoặc chat với cửa hàng.",
                "timeout"=>"Trợ lý AI phản hồi quá lâu. Bạn có thể thử lại hoặc chat với cửa hàng.",
                _=>"Chưa thể nhận câu trả lời AI. Vui lòng thử lại hoặc chat với cửa hàng."
            };
            return StatusCode(reply.Category=="quota"?429:503,new {message});
        }
        // Re-read after network latency; cards remain authoritative even if stock/price changed meanwhile.
        var current=await StoreCatalog.AiContextAsync(db,retrievalQuestion,ct);
        var selected=current.Products.Where(p=>reply.ProductIds?.Contains(p.Id)==true).ToArray();
        var policy=$"Phí giao hàng: {GreenShop.Web.Models.StoreDisplay.Money(current.ShippingFee)}. "+
            (current.FreeShippingThreshold>0?$"Miễn phí từ {GreenShop.Web.Models.StoreDisplay.Money(current.FreeShippingThreshold)}.":"Miễn phí cho mọi giá trị đơn hàng.");
        return Json(new {answer=reply.Answer,products=selected,policy,
            conversation=history.Write(turns.Append(new AiTurn("assistant",reply.Answer)).ToArray(),binding)});
    }
}
