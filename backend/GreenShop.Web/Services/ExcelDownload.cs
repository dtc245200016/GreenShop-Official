using System.Data.Common;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore.Storage;

namespace GreenShop.Web.Services;

public sealed class ExcelExportException(int status, string message) : Exception(message)
{
    public int Status { get; } = status;
}

public static class ExcelExportPolicy
{
    public const string MimeType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
    public static int MaxRows(IConfiguration configuration) =>
        int.TryParse(configuration["ExcelExport:MaxRows"],out var limit) && limit is >=1 and <=20000 ? limit : 20000;
    public static int LowStockThreshold(IConfiguration configuration) =>
        int.TryParse(configuration["Dashboard:LowStockThreshold"],out var threshold) && threshold is >=1 and <=10000 ? threshold : 5;
    public static void CheckCount(int count, int limit)
    {
        if (count>limit) throw new ExcelExportException(422,$"Số lượng dữ liệu vượt giới hạn xuất ({limit:N0} dòng). Vui lòng thu hẹp bộ lọc.");
    }
}

public static class ExcelDownload
{
    // ClosedXML constructs a workbook in memory. Bound concurrent work as well as row count.
    private static readonly SemaphoreSlim Gate = new(1,1);
    public static ObjectResult Error(int status, string message)
    {
        var result=new ObjectResult(new {message}) {StatusCode=status};
        result.ContentTypes.Add("application/json");
        return result;
    }

    public static async Task<IActionResult> RunAsync(Func<CancellationToken,Task<MemoryStream>> generate,
        string prefix, ILogger logger, CancellationToken ct)
    {
        if (!await Gate.WaitAsync(0,ct)) return Error(429,"Một file Excel đang được chuẩn bị. Vui lòng thử lại sau ít giây.");
        MemoryStream? stream=null;
        try
        {
            stream=await generate(ct);
            ct.ThrowIfCancellationRequested();
            var now=TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow,GreenShop.Web.Models.DashboardPeriod.Zone);
            // Prefix comes only from program constants; never from client input.
            return new FileStreamResult(stream,ExcelExportPolicy.MimeType) {FileDownloadName=$"GreenShop_{prefix}_{now:yyyy-MM-dd_HHmmss}.xlsx"};
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) {stream?.Dispose();throw;}
        catch (ExcelExportException ex) {stream?.Dispose();return Error(ex.Status,ex.Message);}
        catch (Exception ex) when (ex is DbException or RetryLimitExceededException)
        {
            stream?.Dispose();logger.LogWarning("Không thể đọc database để xuất Excel.");
            return Error(503,"Chưa thể đọc dữ liệu để xuất Excel. Vui lòng thử lại sau.");
        }
        catch (Exception ex)
        {
            stream?.Dispose();logger.LogError("Không thể tạo file Excel ({ExceptionType}).",ex.GetType().Name);
            return Error(500,"Không thể tạo file Excel. Vui lòng thử lại.");
        }
        finally {Gate.Release();}
    }
}
