using System.Data;
using System.Security.Cryptography;
using System.Text.Json;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

// One transaction/order/inventory path for Buy Now, cart, COD and VietQR.
public class CheckoutOrders(AppDbContext db,IDataProtectionProvider protection)
{
    private readonly IDataProtector cartProtector=protection.CreateProtector("GreenShop.Checkout.CartQuote.v1");
    public Task<PaymentShippingSettings> SettingsAsync(CancellationToken ct) => db.PaymentShippingSettings.AsNoTracking().SingleAsync(s=>s.Id==1,ct);
    public async Task<IReadOnlyList<CheckoutLine>> CartAsync(int userId,CancellationToken ct) => await db.CartItems.AsNoTracking()
        .Where(i=>i.UserId==userId).OrderBy(i=>i.ProductId)
        .Select(i=>new CheckoutLine(i.ProductId,i.Product.Name,i.Product.ImageUrl,i.Product.Price,i.Quantity,
            i.Product.CategoryId==null || i.Product.Category!.IsActive ? i.Product.StockQuantity : -1)).ToListAsync(ct);
    public string QuoteCart(int userId,IReadOnlyList<CheckoutLine> lines) => cartProtector.Protect(QuoteText(userId,lines));
    private static string QuoteText(int userId,IReadOnlyList<CheckoutLine> lines) => JsonSerializer.Serialize(new {userId,items=lines.Select(i=>new {i.ProductId,i.Quantity,i.Price}).OrderBy(i=>i.ProductId)});
    private bool ValidCartQuote(int userId,IReadOnlyList<CheckoutLine> lines,string? quote)
    {
        if(string.IsNullOrEmpty(quote) || quote.Length>100000) return false;
        try{return cartProtector.Unprotect(quote)==QuoteText(userId,lines);}
        catch(CryptographicException){return false;}
    }

    public Task<CheckoutResult> CreateAsync(int userId,long sessionVersion,int? productId,CheckoutViewModel form,CancellationToken ct) =>
        db.Database.CreateExecutionStrategy().ExecuteAsync(async()=>
    {
        db.ChangeTracker.Clear();
        await using var transaction=await db.Database.BeginTransactionAsync(IsolationLevel.ReadCommitted,ct);
        var user=await ShoppingIdentity.LockUserAsync(db,userId,ct);
        if(user==null || !user.IsActive || user.Role!=UserRole.Customer || user.SessionVersion!=sessionVersion) return new CheckoutResult(403,0,"Tài khoản không còn phiên đăng nhập hợp lệ.");
        var existing=await db.Orders.AsNoTracking().FirstOrDefaultAsync(o=>o.UserId==userId && o.ConfirmationToken==form.ConfirmationToken,ct);
        if(existing!=null) return new CheckoutResult(200,existing.Id,"Đơn hàng đã được ghi nhận.");
        var policy=(await db.PaymentShippingSettings.FromSqlRaw("SELECT * FROM PaymentShippingSettings WHERE Id=1 FOR UPDATE").AsNoTracking().ToListAsync(ct)).Single();
        if(policy.Version!=form.PolicyVersion) return new CheckoutResult(409,0,"Chính sách thanh toán hoặc phí vận chuyển đã thay đổi. Vui lòng kiểm tra tổng tiền mới và xác nhận lại.");
        if(!PaymentMethods.Valid(form.PaymentMethod)) return new CheckoutResult(400,0,"Phương thức thanh toán không hợp lệ.");
        if(form.PaymentMethod==PaymentMethods.VietQr && !VietQrImages.Enabled(policy)) return new CheckoutResult(409,0,"Chuyển khoản VietQR hiện chưa khả dụng. Bạn có thể chọn COD.");
        IReadOnlyList<CheckoutLine> lines;
        if(productId.HasValue)
        {
            var product=await StoreCatalog.Saleable(db).AsNoTracking().FirstOrDefaultAsync(p=>p.Id==productId,ct);
            if(product==null) return new CheckoutResult(404,0,"Sản phẩm không còn được bán.");
            if(product.Price!=form.QuotedPrice) return new CheckoutResult(409,0,"Giá đã thay đổi. Vui lòng kiểm tra giá mới và xác nhận lại.");
            lines=new[]{new CheckoutLine(product.Id,product.Name,product.ImageUrl,product.Price,form.Quantity,product.StockQuantity)};
        }
        else
        {
            lines=await CartAsync(userId,ct);
            if(lines.Count==0) return new CheckoutResult(422,0,"Giỏ hàng đang trống.");
            if(lines.Count>100) return new CheckoutResult(422,0,"Mỗi đơn hỗ trợ tối đa 100 loại sản phẩm. Vui lòng điều chỉnh giỏ hàng.");
            if(!ValidCartQuote(userId,lines,form.CartQuote)) return new CheckoutResult(409,0,"Giỏ hàng hoặc giá đã thay đổi. Vui lòng kiểm tra lại trước khi đặt hàng.");
        }
        if(lines.Any(i=>i.Quantity<1 || i.Quantity>1000000 || i.Price<=0 || i.Quantity>i.StockQuantity)) return new CheckoutResult(409,0,"Số lượng vượt tồn kho hoặc sản phẩm đã ngừng bán. Vui lòng kiểm tra lại.");
        var subtotal=lines.Sum(i=>i.Price*i.Quantity);var fee=ShippingFees.Calculate(subtotal,policy);var total=subtotal+fee;
        if(total>9999999999999999.99m) return new CheckoutResult(422,0,"Tổng tiền vượt giới hạn cho phép.");
        if(form.PaymentMethod==PaymentMethods.VietQr && !VietQrImages.AmountValid(total)) return new CheckoutResult(422,0,"VietQR hỗ trợ số tiền VNĐ nguyên, tối đa 13 chữ số. Vui lòng chọn COD cho đơn này.");
        foreach(var line in lines.OrderBy(i=>i.ProductId))
        {
            var changed=await StoreCatalog.Saleable(db).Where(p=>p.Id==line.ProductId && p.Price==line.Price && p.StockQuantity>=line.Quantity)
                .ExecuteUpdateAsync(s=>s.SetProperty(p=>p.StockQuantity,p=>p.StockQuantity-line.Quantity),ct);
            if(changed!=1) return new CheckoutResult(409,0,"Tồn kho hoặc trạng thái sản phẩm đã thay đổi. Toàn bộ đơn chưa được tạo.");
        }
        var order=new Order
        {
            UserId=userId,ConfirmationToken=form.ConfirmationToken,CreatedAt=DateTime.UtcNow,RecipientName=form.RecipientName.Trim(),Phone=form.Phone.Trim(),Address=form.Address.Trim(),
            Status=OrderStatus.Pending,PaymentMethod=form.PaymentMethod,IsPaid=false,Subtotal=subtotal,ShippingFee=fee,Total=total,
            ShippingFlatFeeSnapshot=policy.FlatShippingFee,FreeShippingThresholdSnapshot=policy.FreeShippingThreshold,InventoryStatus=OrderInventoryStatus.Deducted,
            Items=lines.Select(i=>new OrderItem{ProductId=i.ProductId,ProductName=i.Name,ImageUrl=i.ImageUrl,UnitPrice=i.Price,Quantity=i.Quantity}).ToList()
        };
        if(form.PaymentMethod==PaymentMethods.VietQr)
        {
            order.BankBinSnapshot=policy.BankBin;order.BankNameSnapshot=policy.BankName;order.BankAccountSnapshot=policy.AccountNumber;order.BankHolderSnapshot=policy.AccountHolderName;
        }
        db.Orders.Add(order);await db.SaveChangesAsync(ct);
        if(form.PaymentMethod==PaymentMethods.VietQr) {order.TransferContent="GS"+order.Id;await db.SaveChangesAsync(ct);}
        if(!productId.HasValue) await db.CartItems.Where(i=>i.UserId==userId).ExecuteDeleteAsync(ct);
        await AdminNotifications.AddAsync(db,"order:"+order.Id,"Order","Đơn hàng mới #"+order.Id,"/Admin/DonHang/ChiTietDonHang/"+order.Id,ct);
        await transaction.CommitAsync(ct);
        return new CheckoutResult(200,order.Id,"Đã nhận đơn hàng. Thanh toán được ghi nhận riêng.",Created:true);
    });
}
