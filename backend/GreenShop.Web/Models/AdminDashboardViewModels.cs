using System.Globalization;

namespace GreenShop.Web.Models;

public record DashboardPeriod(string Range, string Label, DateTime LocalStart, DateTime LocalEnd, DateTime GeneratedAt)
{
    public static TimeZoneInfo Zone { get; } = TimeZoneInfo.FindSystemTimeZoneById("Asia/Ho_Chi_Minh");
    public DateTime StartUtc => TimeZoneInfo.ConvertTimeToUtc(LocalStart, Zone);
    public DateTime EndUtc => TimeZoneInfo.ConvertTimeToUtc(LocalEnd, Zone);
    public DateTime PreviousStartUtc => StartUtc.AddDays(-(LocalEnd - LocalStart).Days);
    public static DashboardPeriod Create(string? range, DateTime utcNow)
    {
        var now = TimeZoneInfo.ConvertTimeFromUtc(utcNow, Zone);
        range = range is "7d" or "30d" or "month" or "year" ? range : "30d";
        var start = range switch
        {
            "7d" => now.Date.AddDays(-6), "month" => new DateTime(now.Year,now.Month,1),
            "year" => new DateTime(now.Year,1,1), _ => now.Date.AddDays(-29)
        };
        var label = range switch { "7d" => "7 ngày gần nhất", "month" => "Tháng hiện tại", "year" => "Năm hiện tại", _ => "30 ngày gần nhất" };
        return new(range,label,DateTime.SpecifyKind(start,DateTimeKind.Unspecified),DateTime.SpecifyKind(now.Date.AddDays(1),DateTimeKind.Unspecified),now);
    }
    public static string LocalTime(DateTime utc) => TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc,DateTimeKind.Utc),Zone).ToString("dd/MM/yyyy HH:mm");
}

public record DashboardPoint(string Key, string Label, decimal Value);
public record DashboardStatus(OrderStatus Status, int Count);
public class DashboardProduct
{
    public int? Id { get; set; }
    public string Name { get; set; } = "";
    public string ImageUrl { get; set; } = "";
    public decimal? Price { get; set; }
    public long Sold { get; set; }
    public int Stock { get; set; }
}
public class AdminDashboardViewModel
{
    public DashboardPeriod Period { get; set; } = DashboardPeriod.Create(null,DateTime.UtcNow);
    public bool Unavailable { get; set; }
    public int Orders { get; set; }
    public decimal DeliveredValue { get; set; }
    public long Sold { get; set; }
    public int NewCustomers { get; set; }
    public int Shipping { get; set; }
    public int Pending { get; set; }
    public int PreviousOrders { get; set; }
    public decimal PreviousValue { get; set; }
    public long PreviousSold { get; set; }
    public int PreviousCustomers { get; set; }
    public int PendingNow { get; set; }
    public int ProcessingNow { get; set; }
    public int UnpaidCodNow { get; set; }
    public int? UnpaidCodId { get; set; }
    public int PendingTransfersNow { get; set; }
    public int? PendingTransferId { get; set; }
    public int OutOfStock { get; set; }
    public int LowStock { get; set; }
    public int StockThreshold { get; set; } = 5;
    public int ProductCount { get; set; }
    public IReadOnlyList<DashboardPoint> Points { get; set; } = Array.Empty<DashboardPoint>();
    public IReadOnlyList<DashboardStatus> Statuses { get; set; } = Array.Empty<DashboardStatus>();
    public IReadOnlyList<AdminOrderRow> RecentOrders { get; set; } = Array.Empty<AdminOrderRow>();
    public IReadOnlyList<DashboardProduct> BestSellers { get; set; } = Array.Empty<DashboardProduct>();
    public IReadOnlyList<DashboardProduct> StockAlerts { get; set; } = Array.Empty<DashboardProduct>();
    public static string Comparison(decimal current, decimal previous) => previous <= 0 ? "Chưa đủ dữ liệu so sánh"
        : (current >= previous ? "+" : "") + ((current-previous)/previous*100).ToString("0.#",CultureInfo.GetCultureInfo("vi-VN")) + "% so với kỳ trước";
}
