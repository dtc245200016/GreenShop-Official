using GreenShop.Web.Models;

namespace GreenShop.Web.Services;

// List and export share the same UTC date boundaries, filters and stable ordering.
public static class AdminOrderQueries
{
    public static bool Valid(AdminOrderFilter filter) =>
        (!filter.Status.HasValue || Enum.IsDefined(filter.Status.Value))
        && filter.PageSize is 15 or 30 or 50
        && filter.Sort is "newest" or "oldest" or "total-desc" or "total-asc"
        && !(filter.FromDate > filter.ToDate) && filter.ToDate != DateOnly.MaxValue;

    public static IQueryable<Order> Apply(IQueryable<Order> query, AdminOrderFilter filter)
    {
        if (filter.CustomerId.HasValue) query = query.Where(o => o.UserId == filter.CustomerId.Value);
        if (filter.Status.HasValue) query = query.Where(o => o.Status == filter.Status.Value);
        if(filter.PaymentMethod!=null) query=query.Where(o=>o.PaymentMethod==filter.PaymentMethod);
        if(filter.PaymentState=="paid") query=query.Where(o=>o.IsPaid);
        if(filter.PaymentState=="unpaid") query=query.Where(o=>!o.IsPaid);
        if(filter.PaymentState=="pending") query=query.Where(o=>!o.IsPaid && o.PaymentMethod==PaymentMethods.VietQr && o.CustomerTransferNotifiedAt!=null && o.Status!=OrderStatus.Cancelled);
        if (filter.FromDate.HasValue)
        {
            var start = filter.FromDate.Value.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc);
            query = query.Where(o => o.CreatedAt >= start);
        }
        if (filter.ToDate.HasValue)
        {
            var end = filter.ToDate.Value.ToDateTime(TimeOnly.MinValue, DateTimeKind.Utc).AddDays(1);
            query = query.Where(o => o.CreatedAt < end);
        }
        if (!string.IsNullOrEmpty(filter.Search))
        {
            var term = filter.Search;
            var code = term.StartsWith("GS-", StringComparison.OrdinalIgnoreCase) ? term[3..] : term.TrimStart('#');
            int.TryParse(code, out var codeId);
            query = query.Where(o => o.Id == codeId || o.RecipientName.Contains(term) || o.User.FullName.Contains(term) || o.User.Email.Contains(term));
        }
        return filter.Sort switch
        {
            "oldest" => query.OrderBy(o => o.CreatedAt).ThenBy(o => o.Id),
            "total-desc" => query.OrderByDescending(o => o.Total).ThenByDescending(o => o.Id),
            "total-asc" => query.OrderBy(o => o.Total).ThenBy(o => o.Id),
            _ => query.OrderByDescending(o => o.CreatedAt).ThenByDescending(o => o.Id)
        };
    }
}
