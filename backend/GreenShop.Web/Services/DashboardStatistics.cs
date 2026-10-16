using System.Data;
using GreenShop.Web.Data;
using GreenShop.Web.Models;
using Microsoft.EntityFrameworkCore;

namespace GreenShop.Web.Services;

public class DashboardStatistics(AppDbContext db)
{
    public Task<AdminDashboardViewModel> LoadAsync(DashboardPeriod period, int threshold, CancellationToken ct) =>
        db.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
    {
        // A consistent read snapshot keeps all widgets aligned; no transaction data is modified.
        await using var snapshot = await db.Database.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        var model=await ReadAsync(period,threshold,ct);
        await snapshot.CommitAsync(ct);
        return model;
    });

    public Task<DashboardExportReport> LoadReportAsync(DashboardPeriod period,int threshold,int limit,CancellationToken ct) =>
        db.Database.CreateExecutionStrategy().ExecuteAsync(async () =>
    {
        await using var snapshot=await db.Database.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        var model=await ReadAsync(period,threshold,ct);
        var start=period.StartUtc;var end=period.EndUtc;
        var rows=await db.Orders.AsNoTracking().Where(o=>o.CreatedAt>=start && o.CreatedAt<end && o.Status==OrderStatus.Completed)
            .OrderByDescending(o=>o.CreatedAt).ThenByDescending(o=>o.Id).Select(OrderExportRow.Projection).Take(limit+1).ToListAsync(ct);
        ExcelExportPolicy.CheckCount(rows.Count,limit);
        await snapshot.CommitAsync(ct);
        return new DashboardExportReport(model,rows);
    });

    private async Task<AdminDashboardViewModel> ReadAsync(DashboardPeriod period,int threshold,CancellationToken ct)
    {
        var start = period.StartUtc; var end = period.EndUtc; var previousStart = period.PreviousStartUtc;
        var orders = db.Orders.AsNoTracking().Where(o=>o.CreatedAt>=start && o.CreatedAt<end);
        var previous = db.Orders.AsNoTracking().Where(o=>o.CreatedAt>=previousStart && o.CreatedAt<start);
        var counts = await orders.GroupBy(o=>o.Status).Select(g=>new {Status=g.Key,Count=g.Count()}).ToDictionaryAsync(x=>x.Status,x=>x.Count,ct);
        var monthly = period.Range == "year";
        var buckets = await orders.GroupBy(o=>new {Year=o.CreatedAt.AddHours(7).Year,Month=o.CreatedAt.AddHours(7).Month,Day=monthly ? 1 : o.CreatedAt.AddHours(7).Day})
            .Select(g=>new {g.Key.Year,g.Key.Month,g.Key.Day,Value=g.Sum(o=>o.Status==OrderStatus.Completed ? o.Total : 0)})
            .ToListAsync(ct);
        var previousStats = await previous.GroupBy(o=>1).Select(g=>new {Count=g.Count(),Value=g.Sum(o=>o.Status==OrderStatus.Completed ? o.Total : 0)}).FirstOrDefaultAsync(ct);
        var customers = db.Users.AsNoTracking().Where(u=>u.Role==UserRole.Customer);
        var model = new AdminDashboardViewModel
        {
            Period=period,StockThreshold=threshold,Orders=counts.Values.Sum(),DeliveredValue=buckets.Sum(b=>b.Value),
            Pending=counts.GetValueOrDefault(OrderStatus.Pending),Shipping=counts.GetValueOrDefault(OrderStatus.Shipping),
            NewCustomers=await customers.CountAsync(u=>u.CreatedAt>=start && u.CreatedAt<end,ct),
            PreviousCustomers=await customers.CountAsync(u=>u.CreatedAt>=previousStart && u.CreatedAt<start,ct),
            PreviousOrders=previousStats?.Count??0,PreviousValue=previousStats?.Value??0,
            Sold=await db.OrderItems.AsNoTracking().Where(i=>i.Order.Status==OrderStatus.Completed && i.Order.CreatedAt>=start && i.Order.CreatedAt<end).SumAsync(i=>(long?)i.Quantity,ct)??0,
            PreviousSold=await db.OrderItems.AsNoTracking().Where(i=>i.Order.Status==OrderStatus.Completed && i.Order.CreatedAt>=previousStart && i.Order.CreatedAt<start).SumAsync(i=>(long?)i.Quantity,ct)??0,
            Statuses=OrderWorkflow.States.Select(s=>new DashboardStatus(s,counts.GetValueOrDefault(s))).ToArray()
        };
        var values = buckets.ToDictionary(b=>new DateTime(b.Year,b.Month,b.Day),b=>b.Value);
        var points = new List<DashboardPoint>();
        for (var day=period.LocalStart; day<period.LocalEnd; day=monthly ? day.AddMonths(1) : day.AddDays(1))
            points.Add(new(day.ToString(monthly ? "yyyy-MM" : "yyyy-MM-dd"),day.ToString(monthly ? "MM/yyyy" : "dd/MM"),values.GetValueOrDefault(day)));
        model.Points=points;
        model.RecentOrders=await orders.OrderByDescending(o=>o.CreatedAt).ThenByDescending(o=>o.Id).Take(7).Select(o=>new AdminOrderRow
        {
            Id=o.Id,CustomerName=o.User.FullName,CreatedAt=o.CreatedAt,Total=o.Total,Status=o.Status,IsPaid=o.IsPaid,PaymentMethod=o.PaymentMethod,CustomerTransferNotifiedAt=o.CustomerTransferNotifiedAt
        }).ToListAsync(ct);
        var ranked=db.OrderItems.AsNoTracking().Where(i=>i.Order.Status==OrderStatus.Completed && i.Order.CreatedAt>=start && i.Order.CreatedAt<end)
            .GroupBy(i=>new {i.ProductId,HistoricalName=i.ProductId==null ? i.ProductName : ""})
            .Select(g=>new {g.Key.ProductId,g.Key.HistoricalName,Name=g.Max(i=>i.ProductName),Image=g.Max(i=>i.ImageUrl),Sold=g.Sum(i=>(long)i.Quantity)});
        model.BestSellers=await (from rank in ranked
            join product in db.Products.AsNoTracking() on rank.ProductId equals (int?)product.Id into products
            from product in products.DefaultIfEmpty()
            orderby rank.Sold descending,rank.ProductId,rank.HistoricalName
            select new DashboardProduct {Id=rank.ProductId,Name=product==null ? rank.Name! : product.Name,ImageUrl=product==null ? rank.Image! : product.ImageUrl,
                Price=product==null ? null : product.Price,Sold=rank.Sold}).Take(5).ToListAsync(ct);
        var stock=await db.Products.AsNoTracking().GroupBy(p=>1).Select(g=>new {Total=g.Count(),Out=g.Count(p=>p.StockQuantity==0),Low=g.Count(p=>p.StockQuantity>0 && p.StockQuantity<=threshold)}).FirstOrDefaultAsync(ct);
        model.ProductCount=stock?.Total??0;model.OutOfStock=stock?.Out??0;model.LowStock=stock?.Low??0;
        model.StockAlerts=await db.Products.AsNoTracking().Where(p=>p.StockQuantity<=threshold).OrderBy(p=>p.StockQuantity).ThenBy(p=>p.Id).Take(5)
            .Select(p=>new DashboardProduct {Id=p.Id,Name=p.Name,ImageUrl=p.ImageUrl,Stock=p.StockQuantity,Price=p.Price}).ToListAsync(ct);
        var current=await db.Orders.AsNoTracking().GroupBy(o=>1).Select(g=>new {
            Pending=g.Count(o=>o.Status==OrderStatus.Pending),Processing=g.Count(o=>o.Status==OrderStatus.Processing),
            Cod=g.Count(o=>o.Status==OrderStatus.Completed && !o.IsPaid && o.PaymentMethod=="COD"),
            CodId=g.Min(o=>o.Status==OrderStatus.Completed && !o.IsPaid && o.PaymentMethod=="COD" ? (int?)o.Id : null),
            Transfers=g.Count(o=>o.PaymentMethod==PaymentMethods.VietQr && !o.IsPaid && o.Status!=OrderStatus.Cancelled && o.CustomerTransferNotifiedAt!=null),
            TransferId=g.Min(o=>o.PaymentMethod==PaymentMethods.VietQr && !o.IsPaid && o.Status!=OrderStatus.Cancelled && o.CustomerTransferNotifiedAt!=null ? (int?)o.Id : null)}).FirstOrDefaultAsync(ct);
        model.PendingNow=current?.Pending??0;model.ProcessingNow=current?.Processing??0;model.UnpaidCodNow=current?.Cod??0;
        model.UnpaidCodId=current?.CodId;
        model.PendingTransfersNow=current?.Transfers??0;model.PendingTransferId=current?.TransferId;
        return model;
    }
}
