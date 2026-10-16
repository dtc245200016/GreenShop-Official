using ClosedXML.Excel;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Validation;
using GreenShop.Web.Models;
using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using System.IO.Compression;
using System.Text.Json;
using System.Globalization;

static void Check(bool condition,string message) {if(!condition) throw new Exception(message);}
if(args[0]=="payment-rules")
{
    var policy=new PaymentShippingSettings();
    foreach(var (subtotal,fee,total) in new[]{(89000m,30000m,119000m),(250000m,30000m,280000m),(299999m,30000m,329999m),(300000m,0m,300000m),(450000m,0m,450000m)})
        Check(ShippingFees.Calculate(subtotal,policy)==fee && subtotal+fee==total,"Official shipping boundary cases");
    policy.FreeShippingThreshold=0;Check(ShippingFees.Calculate(1,policy)==0,"Zero threshold does not divide by zero");
    Check(!VietQrImages.AmountValid(.01m) && !VietQrImages.AmountValid(10000000000000m) && VietQrImages.AmountValid(9999999999999m),"VND integer and 13-digit amount limits");
    var order=new Order{Id=999,PaymentMethod=PaymentMethods.VietQr,Total=119000,BankBinSnapshot="970436",BankAccountSnapshot="0000000000000000000",BankHolderSnapshot="NGUYỄN VĂN QA",TransferContent="GS999",Address="PRIVATE_ADDRESS",Phone="PRIVATE_PHONE",RecipientName="PRIVATE_RECIPIENT"};
    var url=VietQrImages.ForOrder(order)!;Check(url.StartsWith("https://img.vietqr.io/image/970436-0000000000000000000-compact2.png?") && url.Contains("amount=119000") && url.Contains("addInfo=GS999") && Uri.UnescapeDataString(url).Contains("NGUYỄN VĂN QA") && !url.Contains("PRIVATE"),"Exact safe snapshot URL, URL encoding and no customer PII");
    order.CustomerTransferNotifiedAt=DateTime.UtcNow;Check(!order.IsPaid && PaymentMethods.Status(order)=="Chờ kiểm tra chuyển khoản","Notify does not imply Paid");
    order.IsPaid=true;Check(VietQrImages.ForOrder(order)==null,"Paid does not request more transfer");order.IsPaid=false;order.Status=OrderStatus.Cancelled;Check(VietQrImages.ForOrder(order)==null,"Cancelled has no payment QR");
    order.Items.Add(new OrderItem{Quantity=1,UnitPrice=89000});order.Total=89000;Check(PaymentMethods.ValidMoney(order),"Legacy totals preserved without assuming shipping");
    order.Subtotal=89000;order.ShippingFee=30000;order.Total=119000;Check(PaymentMethods.ValidMoney(order),"New stored monetary snapshots");order.Total=119001;Check(!PaymentMethods.ValidMoney(order),"Mismatched total rejected");
    Console.WriteLine("PASS: Production shipping/amount boundaries, snapshot URL/encoding/privacy, paid-cancelled QR suppression and legacy/new monetary validation.");
    File.WriteAllText(Path.Combine(args[1],"payment-rules-results.json"),JsonSerializer.Serialize(new{status="PASS",checks="Shipping boundary matrix, amount/QR encoding/privacy, paid/cancelled states, legacy/new money"}));
    return;
}
var folder=Path.GetFullPath(args[0]);var files=Directory.GetFiles(folder,"*.expected.json");
foreach(var file in files)
{
    using var expected=JsonDocument.Parse(File.ReadAllText(file));var root=expected.RootElement;
    var path=Path.Combine(folder,root.GetProperty("file").GetString()!);
    using(var zip=ZipFile.OpenRead(path))
    {
        Check(zip.GetEntry("xl/workbook.xml")!=null && zip.GetEntry("[Content_Types].xml")!=null,"Open XML ZIP structure");
        Check(!zip.Entries.Any(e=>e.FullName.Contains("externalLink") || e.FullName.Contains("vbaProject")),"No macros/external links");
    }
    using(var xml=SpreadsheetDocument.Open(path,false))
        Check(!new OpenXmlValidator().Validate(xml).Any(),"Open XML schema validation: "+Path.GetFileName(path));
    using var book=new XLWorkbook(path);
    var sheets=root.GetProperty("sheets").EnumerateArray().ToArray();
    Check(book.Worksheets.Count==sheets.Length,"Worksheet count");
    foreach(var spec in sheets)
    {
        var sheet=book.Worksheet(spec.GetProperty("name").GetString()!);
        Check(sheet.Cell(1,1).GetString().StartsWith("GREENSHOP"),"Brand header");
        Check(sheet.Cell(3,2).DataType==XLDataType.DateTime,"Real export timestamp");
        Check(sheet.SheetView.SplitRow==7 && sheet.AutoFilter.IsEnabled,"Frozen headers and filter");
        var headers=spec.GetProperty("headers").EnumerateArray().Select(e=>e.GetString()).ToArray();
        for(var col=0;col<headers.Length;col++) Check(sheet.Cell(7,col+1).GetString()==headers[col],"Column header");
        var rows=spec.GetProperty("rows").EnumerateArray().ToArray();
        for(var row=0;row<rows.Length;row++)
        {
            var cells=rows[row].EnumerateArray().ToArray();
            for(var col=0;col<cells.Length;col++)
            {
                var cell=sheet.Cell(8+row,col+1);var value=cells[col];
                Check(!cell.HasFormula,"Formula injection");
                if(value.ValueKind==JsonValueKind.Number)
                {
                    Check(cell.DataType==XLDataType.Number,"Numeric money/quantity");
                    Check(Math.Abs(cell.GetDouble()-value.GetDouble())<.005,"Exact numeric value");
                    if(headers[col] is "Giá bán" or "Giá trị đơn đã giao" or "Tổng thanh toán" or "Tiền sản phẩm đã lưu" or "Phí vận chuyển đã lưu") Check(cell.Style.NumberFormat.Format.Contains('₫'),"Money number format");
                }
                else if(value.ValueKind==JsonValueKind.Object)
                {
                    Check(cell.DataType==XLDataType.DateTime,"Real Excel date");
                    Check(Math.Abs((cell.GetDateTime()-DateTime.Parse(value.GetProperty("date").GetString()!,CultureInfo.InvariantCulture)).TotalMilliseconds)<1,"Date/time value within Excel millisecond resolution");
                    Check(cell.Style.NumberFormat.Format.Contains("MM"),"Date number format");
                }
                else if(value.ValueKind==JsonValueKind.Null) Check(cell.DataType is XLDataType.Text or XLDataType.Blank && cell.GetString()=="","Historical unrecorded value stays blank");
                else Check(cell.DataType is XLDataType.Text or XLDataType.Blank && cell.GetString()==value.GetString(),"Exact safe text");
            }
        }
        // Only controlled headers/data and the intentionally separated totals row are present.
        var totalRow=spec.TryGetProperty("totalRow",out var tr) ? tr.GetInt32() : 0;
        Check(sheet.LastRowUsed()!.RowNumber()==(totalRow>0 ? totalRow : rows.Length+7),"No missing/extra rows");
        Check(sheet.LastColumnUsed()!.ColumnNumber()==headers.Length,"No extra columns");
        Check(!sheet.CellsUsed().Any(c=>c.HasFormula || c.HasHyperlink),"No user-controlled formulas/hyperlinks");
    }
    if(root.TryGetProperty("cells",out var specific))
        foreach(var sheetSpec in specific.EnumerateObject())
            foreach(var value in sheetSpec.Value.EnumerateObject())
                Check(Math.Abs(book.Worksheet(sheetSpec.Name).Cell(value.Name).GetDouble()-value.Value.GetDouble())<.005,"Totals match metadata");
    using var saved=new MemoryStream();book.SaveAs(saved);saved.Position=0;using var again=new XLWorkbook(saved);
    Check(again.Worksheets.Count==book.Worksheets.Count,"ClosedXML save/reopen");
    foreach(var sheet in book.Worksheets)
        foreach(var cell in sheet.CellsUsed())
        {
            var other=again.Worksheet(sheet.Name).Cell(cell.Address);
            Check(cell.DataType==other.DataType && cell.Value.Equals(other.Value),"Round-trip cell type/value");
        }
    Console.WriteLine("PASS: "+Path.GetFileName(path)+" — Open XML schema, exact rows/types/values, styles, safe text and ClosedXML round-trip");
}
Check(files.Length>0,"Actual downloaded fixtures required");
try {ExcelExportService.Products(Array.Empty<ProductExportRow>(),5,CancellationToken.None);throw new Exception("Empty products must fail");}
catch(ExcelExportException ex){Check(ex.Status==404,"Clear empty product export");}
// Exercise the shared failure paths without breaking a real database or writing business data.
var log=NullLogger.Instance;
var failed=await ExcelDownload.RunAsync(_=>throw new InvalidOperationException("private technical details"),"Unit",log,CancellationToken.None);
Check(failed is ObjectResult {StatusCode:500},"Generation error is non-file HTTP 500");
Check(!JsonSerializer.Serialize(((ObjectResult)failed).Value).Contains("private"),"Error does not leak details");
var unavailable=await ExcelDownload.RunAsync(_=>throw new TestDatabaseException(),"Unit",log,CancellationToken.None);
Check(unavailable is ObjectResult {StatusCode:503},"Database error is non-file HTTP 503");
using var cancel=new CancellationTokenSource();cancel.Cancel();
try {await ExcelDownload.RunAsync(_=>Task.FromResult(new MemoryStream()),"Unit",log,cancel.Token);throw new Exception("Cancellation required");}
catch(OperationCanceledException) { }
var entered=new TaskCompletionSource();var release=new TaskCompletionSource();
var active=ExcelDownload.RunAsync(async _=>{entered.SetResult();await release.Task;return new MemoryStream(new byte[]{1});},"Unit",log,CancellationToken.None);
await entered.Task;
var blocked=await ExcelDownload.RunAsync(_=>throw new Exception("Must not run"),"Unit",log,CancellationToken.None);
Check(blocked is ObjectResult {StatusCode:429},"Concurrent generation bounded");
release.SetResult();((FileStreamResult)await active).FileStream.Dispose();
var configuration=new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string,string?>{{"ExcelExport:MaxRows","42"},{"Dashboard:LowStockThreshold","9"}}).Build();
Check(ExcelExportPolicy.MaxRows(configuration)==42 && ExcelExportPolicy.LowStockThreshold(configuration)==9,"Configurable limits/stock threshold");
try {ExcelExportPolicy.CheckCount(43,42);throw new Exception("Row limit required");}catch(ExcelExportException ex){Check(ex.Status==422,"Overflow rejects full export");}
Console.WriteLine("PASS: Shared generation/database errors, cancellation, concurrent limit and configurable row/stock limits");
File.WriteAllText(Path.Combine(folder,"closedxml-results.json"),JsonSerializer.Serialize(new {status="PASS",files=files.Length,checks="Open XML validation, exact rows/values/types, styles, formula safety, save/reopen; error/cancellation/concurrency policies"}));

sealed class TestDatabaseException : System.Data.Common.DbException { }
