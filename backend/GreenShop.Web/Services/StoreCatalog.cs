using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;
using System.Linq.Expressions;

namespace GreenShop.Web.Services;

public static class StoreCatalog
{
    public static (decimal? Maximum,bool Exclusive,string[] Terms) AiFilter(string question)
    {
        var normalized=question.ToLowerInvariant();
        var match=System.Text.RegularExpressions.Regex.Match(normalized,@"(?:dưới|duoi|tối đa|toi da|không quá|khong qua|ngân sách|ngan sach)\s*([0-9]+(?:[.,][0-9]+)*)\s*(nghìn|ngàn|nghin|ngan|k|triệu|trieu|đồng|đ|vnd)?");
        decimal? maximum=null;
        if(match.Success) {
            var raw=match.Groups[1].Value;var unit=match.Groups[2].Value;
            var multiplier=unit is "k" or "nghìn" or "ngàn" or "nghin" or "ngan"?1000:unit is "triệu" or "trieu"?1000000:1;
            raw=multiplier==1?raw.Replace(".","").Replace(",",""):raw.Replace(",",".");
            maximum=decimal.TryParse(raw,System.Globalization.NumberStyles.AllowDecimalPoint,System.Globalization.CultureInfo.InvariantCulture,out var amount)?Math.Clamp(amount,0,1000000000m/multiplier)*multiplier:0;
            normalized=normalized.Remove(match.Index,match.Length);
        }
        var generic=new HashSet<string>(("greenshop có những cây nào sản phẩm phù hợp với cho tôi mình bạn muốn tìm mua chọn tư vấn giúp gợi ý không một loại cảnh và ở của là được hãy xin chào dưới tối đa ngân sách đồng bàn làm việc để văn phòng chăm sóc tưới như thế nào cần có thể không quá").Split(' '));
        var terms=System.Text.RegularExpressions.Regex.Matches(normalized,@"[\p{L}][\p{L}\p{N}-]*")
            .Select(m=>m.Value).Where(w=>w.Length>=3 && !generic.Contains(w)).Distinct().Take(8).ToArray();
        // A desk requirement must be supported by public product/category descriptions.
        if(normalized.Contains("bàn làm việc") || normalized.Contains("để bàn") || normalized.Contains("văn phòng")) terms=terms.Concat(new[]{"bàn","văn phòng","desk"}).Take(8).ToArray();
        return (maximum,match.Value.StartsWith("dưới") || match.Value.StartsWith("duoi"),terms);
    }

    public static async Task<AiPublicContext> AiContextAsync(AppDbContext db,string question,CancellationToken ct)
    {
        var filter=AiFilter(question);var query=Saleable(db).Where(p=>p.StockQuantity>0);
        if(filter.Maximum is decimal maximum) query=filter.Exclusive?query.Where(p=>p.Price<maximum):query.Where(p=>p.Price<=maximum);
        // Pomelo 8 does not enable primitive collection query roots. Build a bounded OR
        // expression so filtering stays in SQL instead of failing or loading the whole catalog.
        if(filter.Terms.Length>0) {
            var p=Expression.Parameter(typeof(Product),"p");Expression predicate=Expression.Constant(false);
            var contains=typeof(string).GetMethod(nameof(string.Contains),[typeof(string)])!;
            foreach(var word in filter.Terms) {
                var term=Expression.Constant(word);
                var name=Expression.Call(Expression.Property(p,nameof(Product.Name)),contains,term);
                var description=Expression.Call(Expression.Property(p,nameof(Product.Description)),contains,term);
                var category=Expression.Property(p,nameof(Product.Category));
                var categoryName=Expression.AndAlso(Expression.NotEqual(category,Expression.Constant(null,typeof(Category))),
                    Expression.Call(Expression.Property(category,nameof(Category.Name)),contains,term));
                predicate=Expression.OrElse(predicate,Expression.OrElse(Expression.OrElse(name,description),categoryName));
            }
            query=query.Where(Expression.Lambda<Func<Product,bool>>(predicate,p));
        }
        var needDesk=question.Contains("bàn làm việc",StringComparison.OrdinalIgnoreCase) || question.Contains("để bàn",StringComparison.OrdinalIgnoreCase) || question.Contains("văn phòng",StringComparison.OrdinalIgnoreCase);
        if(needDesk) query=query.Where(p=>p.Name.Contains("bàn") || p.Description.Contains("bàn") || p.Description.Contains("desk") || p.Description.Contains("văn phòng") || (p.Category!=null && (p.Category.Name.Contains("bàn") || p.Category.Name.Contains("văn phòng"))));
        var products=await Project(query.OrderBy(p=>p.Price).ThenBy(p=>p.Id).Take(6),db).ToListAsync(ct);
        static string Bound(string text,int length)=>text.Length>length?text[..length]:text;
        var items=products.Select(p=>new AiCatalogItem(p.Id,Bound(p.Name,150),p.Price,p.StockQuantity,"/SanPham/ChiTietSanPham/"+p.Id,
            Bound(p.Description,800),Bound(p.CategoryName,100),p.AverageStars,p.ReviewCount,StoreDisplay.Image(p.ImageUrl))).ToArray();
        var policy=await db.PaymentShippingSettings.AsNoTracking().SingleAsync(ct);
        return new(items,policy.FlatShippingFee,policy.FreeShippingThreshold);
    }

    public static IQueryable<Product> Saleable(AppDbContext db) => db.Products.AsNoTracking()
        .Where(p => p.CategoryId == null || p.Category!.IsActive);

    public static IQueryable<StoreProductViewModel> Project(IQueryable<Product> products, AppDbContext db) => products.Select(p => new StoreProductViewModel
    {
        Id = p.Id, Name = p.Name, Price = p.Price, ImageUrl = p.ImageUrl, Description = p.Description,
        StockQuantity = p.StockQuantity, CategoryId = p.CategoryId,
        CategoryName = p.Category == null ? "Chưa phân loại" : p.Category.Name,
        ReviewCount = db.ProductReviews.Count(r=>r.IsCurrent && !r.IsHidden && r.ProductId==p.Id),
        AverageStars = db.ProductReviews.Where(r=>r.IsCurrent && !r.IsHidden && r.ProductId==p.Id).Average(r=>(double?)r.Stars),
        SoldCount = db.OrderItems.Where(i => i.ProductId == p.Id && i.Order.Status == OrderStatus.Completed)
            .Sum(i => (long?)i.Quantity) ?? 0
    });

    public static async Task<IReadOnlyList<StoreProductViewModel>> HeroAsync(AppDbContext db, CancellationToken ct)
    {
        var settings=await db.HomeSliderSettings.AsNoTracking().SingleAsync(ct);
        var products=Saleable(db);
        if(settings.Mode=="all") return await Project(products.OrderByDescending(p=>p.Id),db).ToListAsync(ct);
        var start=settings.Days==0 ? DateTime.MinValue : DateTime.UtcNow.AddDays(-settings.Days);
        var sales=db.OrderItems.Where(i=>i.Order.Status==OrderStatus.Completed && i.Order.CreatedAt>=start);
        var ranked=products.OrderByDescending(p=>sales.Where(i=>i.ProductId==p.Id).Sum(i=>(long?)i.Quantity)??0).ThenByDescending(p=>p.Id).Take(settings.ProductCount);
        return await Project(ranked,db).ToListAsync(ct);
    }

    public static async Task<StoreCatalogViewModel?> LoadAsync(AppDbContext db, int? categoryId, string? search, string sort, int page, CancellationToken ct)
    {
        var categories = await db.Categories.AsNoTracking().Where(c => c.IsActive).OrderBy(c => c.Name)
            .Select(c => new StoreCategoryViewModel { Id = c.Id, Name = c.Name, ProductCount = c.Products.Count }).ToListAsync(ct);
        var selected = categories.FirstOrDefault(c => c.Id == categoryId);
        if (categoryId.HasValue && selected == null) return null;
        var query = Saleable(db);
        if (categoryId.HasValue) query = query.Where(p => p.CategoryId == categoryId);
        if (!string.IsNullOrEmpty(search)) query = query.Where(p => p.Name.Contains(search));
        var count = await query.CountAsync(ct);
        var totalPages = Math.Max(1, (int)Math.Ceiling(count / 12d));
        page = Math.Min(page, totalPages);
        var ordered = sort switch
        {
            "price-asc" => query.OrderBy(p => p.Price).ThenByDescending(p => p.Id),
            "price-desc" => query.OrderByDescending(p => p.Price).ThenByDescending(p => p.Id),
            _ => query.OrderByDescending(p => p.Id)
        };
        return new StoreCatalogViewModel
        {
            Categories = categories, CategoryId = categoryId, CategoryName = selected?.Name, Search = search,
            Sort = sort, Page = page, TotalCount = count,
            Products = await Project(ordered.Skip((page - 1) * 12).Take(12), db).ToListAsync(ct)
        };
    }
}
