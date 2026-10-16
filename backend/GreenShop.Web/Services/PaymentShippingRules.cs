using System.Globalization;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using GreenShop.Web.Models;

namespace GreenShop.Web.Services;

public record VietQrBank(string Bin,string Code,string ShortName,string Name);
public static class VietQrBanks
{
    private static readonly JsonSerializerOptions JsonOptions=new(){PropertyNameCaseInsensitive=true};
    private static IReadOnlyList<VietQrBank> banks=LoadFallback();
    private static DateTime refreshedAt=DateTime.MinValue;
    private static readonly SemaphoreSlim RefreshGate=new(1,1);
    private static readonly HttpClient Client=new(){Timeout=TimeSpan.FromSeconds(3)};
    public static IReadOnlyList<VietQrBank> All => Volatile.Read(ref banks);
    public static VietQrBank? Find(string? bin) => All.FirstOrDefault(b=>b.Bin==bin);
    private static IReadOnlyList<VietQrBank> LoadFallback()
    {
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("GreenShop.Web.Data.vietqr-banks.json")!;
        using var document=JsonDocument.Parse(stream);
        return document.RootElement.GetProperty("banks").Deserialize<VietQrBank[]>(JsonOptions)!;
    }
    // Refresh only on the Admin settings page, at most daily. Checkout uses cached data.
    public static async Task RefreshAsync(CancellationToken ct)
    {
        if(DateTime.UtcNow-refreshedAt<TimeSpan.FromDays(1) || !await RefreshGate.WaitAsync(0,ct)) return;
        try
        {
            using var response=await Client.GetAsync("https://api.vietqr.io/v2/banks",ct);
            response.EnsureSuccessStatusCode();
            using var document=JsonDocument.Parse(await response.Content.ReadAsStringAsync(ct));
            if(document.RootElement.GetProperty("code").GetString()!="00") return;
            var records=document.RootElement.GetProperty("data").EnumerateArray().Where(x=>x.GetProperty("transferSupported").GetInt32()==1)
                .Select(x=>new VietQrBank(x.GetProperty("bin").GetString()!,x.GetProperty("code").GetString()!,x.GetProperty("shortName").GetString()!,x.GetProperty("name").GetString()!)).ToArray();
            if(records.Length>20 && records.All(x=>Regex.IsMatch(x.Bin,"^[0-9]{6}$") && x.Name.Length<=200) && records.Select(x=>x.Bin).Distinct().Count()==records.Length)
                Volatile.Write(ref banks,records);
        }
        catch(Exception ex) when(ex is HttpRequestException or TaskCanceledException or JsonException or InvalidOperationException or KeyNotFoundException) { }
        finally {refreshedAt=DateTime.UtcNow;RefreshGate.Release();}
    }
}

public static class ShippingFees
{
    public static decimal Calculate(decimal subtotal,PaymentShippingSettings settings)
    {
        if(subtotal<0 || settings.FlatShippingFee<0 || settings.FreeShippingThreshold<0) throw new InvalidOperationException("Chính sách phí vận chuyển không hợp lệ.");
        return subtotal>=settings.FreeShippingThreshold ? 0 : settings.FlatShippingFee;
    }
}

public static class VietQrImages
{
    public static bool AccountValid(string? bin,string? number,string? holder) =>
        bin!=null && Regex.IsMatch(bin,"^[0-9]{6}$") && number!=null && Regex.IsMatch(number,"^[A-Za-z0-9]{1,19}$")
        && !string.IsNullOrWhiteSpace(holder) && holder.Length<=100 && !holder.Any(char.IsControl);
    public static bool Enabled(PaymentShippingSettings settings) => settings.VietQrEnabled && VietQrBanks.Find(settings.BankBin)!=null && AccountValid(settings.BankBin,settings.AccountNumber,settings.AccountHolderName);
    public static bool AmountValid(decimal amount) => amount>0 && amount<=9999999999999m && amount==decimal.Truncate(amount);
    public static string? ForOrder(Order order)
    {
        if(!PaymentMethods.NeedsTransfer(order) || !AccountValid(order.BankBinSnapshot,order.BankAccountSnapshot,order.BankHolderSnapshot)
            || !AmountValid(order.Total) || order.TransferContent==null || !Regex.IsMatch(order.TransferContent,"^[A-Z0-9]{1,50}$")) return null;
        return Build(order.BankBinSnapshot!,order.BankAccountSnapshot!,order.BankHolderSnapshot!,order.TransferContent,order.Total);
    }
    public static string? Preview(PaymentShippingSettings settings) => AccountValid(settings.BankBin,settings.AccountNumber,settings.AccountHolderName)
        ? Build(settings.BankBin,settings.AccountNumber,settings.AccountHolderName,"GSXEMTRUOC",null) : null;
    private static string Build(string bin,string account,string holder,string description,decimal? amount) =>
        $"https://img.vietqr.io/image/{Uri.EscapeDataString(bin)}-{Uri.EscapeDataString(account)}-compact2.png?addInfo={Uri.EscapeDataString(description)}&accountName={Uri.EscapeDataString(holder)}"
        +(amount.HasValue ? "&amount="+amount.Value.ToString("0",CultureInfo.InvariantCulture) : "");
}
