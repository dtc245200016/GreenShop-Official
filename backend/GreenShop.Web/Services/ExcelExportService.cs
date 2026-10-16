using ClosedXML.Excel;
using GreenShop.Web.Models;
using System.Globalization;

namespace GreenShop.Web.Services;

// Formatting only: callers supply read-only projections and the existing Dashboard metrics.
public static class ExcelExportService
{
    private const int HeaderRow=7;
    private const string MoneyFormat="#,##0.00\" ₫\"";
    private static readonly XLColor Green=XLColor.FromHtml("#205C40");
    private static readonly XLColor Light=XLColor.FromHtml("#EDF5E8");
    private static DateTime Local(DateTime utc) => TimeZoneInfo.ConvertTimeFromUtc(DateTime.SpecifyKind(utc,DateTimeKind.Utc),DashboardPeriod.Zone);

    public static MemoryStream Orders(IReadOnlyList<OrderExportRow> rows, AdminOrderFilter filter, CancellationToken ct)
    {
        if (rows.Count==0) throw new ExcelExportException(404,"Không có dữ liệu phù hợp để xuất.");
        using var book=new XLWorkbook();
        var filters=$"Tìm: {filter.Search??"Tất cả"} · Khách hàng: {filter.CustomerId?.ToString()??"Tất cả"} · Trạng thái: {(filter.Status.HasValue ? OrderWorkflow.Label(filter.Status.Value) : "Tất cả")} · Từ: {filter.FromDate?.ToString("dd/MM/yyyy")??"Không giới hạn"} · Đến hết: {filter.ToDate?.ToString("dd/MM/yyyy")??"Không giới hạn"} · Sắp xếp: {filter.Sort} · Phương thức: {filter.PaymentMethod??"Tất cả"} · Thanh toán: {filter.PaymentState??"Tất cả"}";
        AddOrders(book,"Đơn hàng",rows,"DANH SÁCH ĐƠN HÀNG",filters,
            "Bộ lọc ngày theo UTC như danh sách; ngày đặt hiển thị GMT+7. Tổng thanh toán lấy từ đơn đã lưu; đã giao và đã thanh toán là hai trạng thái riêng.",ct);
        return Save(book,ct);
    }

    public static MemoryStream Products(IReadOnlyList<ProductExportRow> rows, int threshold, CancellationToken ct)
    {
        if (rows.Count==0) throw new ExcelExportException(404,"Không có dữ liệu phù hợp để xuất.");
        using var book=new XLWorkbook();
        var sheet=Sheet(book,"Sản phẩm & tồn kho","SẢN PHẨM & TỒN KHO",7,"Tất cả sản phẩm · Mã mới nhất trước",
            $"Tồn kho hiện tại: 0 = Hết hàng; 1–{threshold} = Sắp hết hàng. Ngưỡng dùng chung với Tổng quan. Sản phẩm chưa có trạng thái kinh doanh hoặc ngày tạo/cập nhật riêng.");
        Headers(sheet,"STT","Mã sản phẩm","Tên sản phẩm","Danh mục","Giá bán","Số lượng tồn kho","Tình trạng tồn kho");
        var r=HeaderRow+1;
        foreach(var item in rows)
        {
            ct.ThrowIfCancellationRequested();
            Row(sheet,r++,r-HeaderRow-1,item.Id,item.Name,item.Category,item.Price,item.Stock,
                item.Stock==0 ? "Hết hàng" : item.Stock<=threshold ? "Sắp hết hàng" : "Còn hàng");
        }
        Table(sheet,r-1,7);sheet.Column(3).Width=38;sheet.Column(4).Width=28;
        sheet.Column(5).Style.NumberFormat.Format=MoneyFormat;
        Row(sheet,r+1,"Tổng tồn kho", "", "", "", "",rows.Sum(x=>(long)x.Stock), "");
        TotalStyle(sheet,r+1,7);
        return Save(book,ct);
    }

    public static MemoryStream Dashboard(DashboardExportReport report, CancellationToken ct)
    {
        var model=report.Dashboard;var p=model.Period;var rows=report.Orders;
        if(model.Orders==0) throw new ExcelExportException(404,"Không có dữ liệu phù hợp để xuất.");
        if(rows.Sum(x=>x.Total)!=model.DeliveredValue) throw new ExcelExportException(503,"Số liệu đối soát chưa khớp. Vui lòng tải lại báo cáo.");
        using var book=new XLWorkbook();
        var period=$"{p.Label}: {p.LocalStart:dd/MM/yyyy} – {p.LocalEnd.AddDays(-1):dd/MM/yyyy} · GMT+7";
        const string rule="Giá trị đơn đã giao = tổng thanh toán đã lưu (gồm phí ship nếu có) của đơn hiện Đã giao, theo ngày đặt tại Việt Nam; loại đơn hủy, không phải doanh thu thực thu hay lợi nhuận. Phí ship/ngày xác nhận thanh toán của đơn cũ có thể chưa được ghi nhận; không tự suy ra hoặc backfill.";
        var summary=Sheet(book,"Tổng quan","BÁO CÁO GIÁ TRỊ ĐƠN ĐÃ GIAO",2,period,rule);
        Headers(summary,"Chỉ số","Giá trị");
        Row(summary,8,"Từ ngày (GMT+7)",p.LocalStart);Row(summary,9,"Đến hết ngày (GMT+7)",p.LocalEnd.AddDays(-1));
        summary.Range("B8:B9").Style.NumberFormat.Format="dd/MM/yyyy";
        Row(summary,10,"Tổng số đơn đặt trong kỳ",model.Orders);
        Row(summary,11,"Số đơn đã giao",rows.Count);
        Row(summary,12,"Số đơn đã hủy",model.Statuses.First(x=>x.Status==OrderStatus.Cancelled).Count);
        Row(summary,13,"Số đơn đã xác nhận / đang xử lý",model.Statuses.Where(x=>x.Status is OrderStatus.Confirmed or OrderStatus.Processing).Sum(x=>x.Count));
        Row(summary,14,"Giá trị đơn đã giao",model.DeliveredValue);summary.Cell(14,2).Style.NumberFormat.Format=MoneyFormat;
        Row(summary,15,"Số lượng sản phẩm đã bán",model.Sold);
        Row(summary,16,"Đơn đã giao chưa xác nhận thanh toán",rows.Count(x=>!x.IsPaid));
        Row(summary,17,"Phí ship đã ghi nhận trong các đơn đã giao",rows.Sum(x=>x.ShippingFee??0));
        Row(summary,18,"Đơn đã giao thiếu chi tiết phí ship",rows.Count(x=>!x.ShippingFee.HasValue));
        Table(summary,18,2);summary.Column(1).Width=56;summary.Column(2).Width=42;
        summary.Range("A4:B5").Style.Alignment.WrapText=true;summary.Row(5).Height=96;
        var timeline=Sheet(book,"Theo thời gian","GIÁ TRỊ ĐƠN ĐÃ GIAO THEO THỜI GIAN",4,period,rule);
        Headers(timeline,p.Range=="year" ? "Tháng (GMT+7)" : "Ngày (GMT+7)","Số đơn đã giao","Giá trị đơn đã giao","Số lượng sản phẩm đã bán");
        var monthly=p.Range=="year";
        var groups=rows.GroupBy(o=>Local(o.CreatedAt).ToString(monthly ? "yyyy-MM" : "yyyy-MM-dd")).ToDictionary(g=>g.Key,g=>new {Count=g.Count(),Quantity=g.Sum(o=>o.Quantity)});
        var r=8;
        foreach(var point in model.Points)
        {
            ct.ThrowIfCancellationRequested();
            var date=DateTime.ParseExact(point.Key,monthly ? "yyyy-MM" : "yyyy-MM-dd",CultureInfo.InvariantCulture);
            groups.TryGetValue(point.Key,out var group);
            Row(timeline,r++,date,group?.Count??0,point.Value,group?.Quantity??0);
        }
        Table(timeline,r-1,4);timeline.Column(1).Style.NumberFormat.Format=monthly ? "MM/yyyy" : "dd/MM/yyyy";
        timeline.Column(3).Style.NumberFormat.Format=MoneyFormat;timeline.Columns(2,4).Width=28;
        Row(timeline,r+1,"Tổng",rows.Count,model.DeliveredValue,model.Sold);TotalStyle(timeline,r+1,4);
        if(rows.Count>0) AddOrders(book,"Đơn hàng liên quan",rows,"ĐƠN ĐÃ GIAO ĐƯỢC TÍNH VÀO BÁO CÁO",period,rule,ct);
        return Save(book,ct);
    }

    private static void AddOrders(XLWorkbook book, string name, IReadOnlyList<OrderExportRow> rows,string title,string filters,string note,CancellationToken ct)
    {
        var sheet=Sheet(book,name,title,18,filters,note+" Ô tiền hàng/phí ship trống là chưa ghi nhận trong đơn cũ.");
        Headers(sheet,"STT","Mã đơn hàng","Ngày đặt (GMT+7)","Tên khách hàng","Người nhận","Điện thoại người nhận","Địa chỉ giao hàng","Số loại sản phẩm","Tổng số lượng","Tiền sản phẩm đã lưu","Phí vận chuyển đã lưu","Tổng thanh toán","Phương thức thanh toán","Trạng thái thanh toán","Trạng thái đơn hàng","Khách báo chuyển khoản (GMT+7)","Xác nhận nhận tiền (GMT+7)","Người xác nhận nhận tiền");
        var r=8;var index=0;
        foreach(var item in rows)
        {
            ct.ThrowIfCancellationRequested();
            Row(sheet,r++,++index,OrderWorkflow.Code(item.Id),Local(item.CreatedAt),item.CustomerName,item.RecipientName,item.Phone,item.Address,item.ItemKinds,item.Quantity,item.Subtotal,item.ShippingFee,item.Total,item.PaymentMethod,
                PaymentMethods.Status(item.IsPaid,item.PaymentMethod,item.CustomerTransferNotifiedAt),OrderWorkflow.Label(item.Status),
                item.CustomerTransferNotifiedAt.HasValue ? Local(item.CustomerTransferNotifiedAt.Value) : null,item.PaidAt.HasValue ? Local(item.PaidAt.Value) : null,item.PaymentConfirmedByName);
        }
        Table(sheet,r-1,18);
        sheet.Column(1).Width=8;sheet.Column(3).Width=24;sheet.Column(4).Width=28;sheet.Column(5).Width=28;sheet.Column(7).Width=42;
        sheet.Column(3).Style.NumberFormat.Format="dd/MM/yyyy HH:mm";sheet.Columns(10,12).Style.NumberFormat.Format=MoneyFormat;
        sheet.Columns(16,17).Style.NumberFormat.Format="dd/MM/yyyy HH:mm";
        Row(sheet,r+1,"Tổng đã ghi nhận", "", "", "", "", "", "", "",rows.Sum(x=>x.Quantity),rows.Sum(x=>x.Subtotal??0),rows.Sum(x=>x.ShippingFee??0),rows.Sum(x=>x.Total), "", "", "", "", "", "");
        TotalStyle(sheet,r+1,18);
    }

    private static IXLWorksheet Sheet(XLWorkbook book,string name,string title,int cols,string filters,string note)
    {
        var sheet=book.Worksheets.Add(name);sheet.Style.Font.FontName="Calibri";sheet.Style.Font.FontSize=11;
        sheet.Style.Font.FontColor=XLColor.FromHtml("#244534");sheet.Style.Alignment.Vertical=XLAlignmentVerticalValues.Center;
        sheet.Range(1,1,1,cols).Merge();Text(sheet.Cell(1,1),"GREENSHOP · "+title);
        sheet.Range(1,1,1,cols).Style.Fill.BackgroundColor=Green;sheet.Range(1,1,1,cols).Style.Font.FontColor=XLColor.White;
        sheet.Row(1).Height=38;sheet.Cell(1,1).Style.Font.FontSize=18;sheet.Cell(1,1).Style.Font.Bold=true;
        Text(sheet.Cell(3,1),"Thời điểm xuất (GMT+7)");sheet.Range(3,2,3,cols).Merge();sheet.Cell(3,2).Value=Local(DateTime.UtcNow);sheet.Cell(3,2).Style.NumberFormat.Format="dd/MM/yyyy HH:mm";
        sheet.Range(4,1,4,cols).Merge();Text(sheet.Cell(4,1),filters);sheet.Row(4).Height=32;
        sheet.Range(5,1,5,cols).Merge();Text(sheet.Cell(5,1),note);sheet.Row(5).Height=48;sheet.Range(4,1,5,cols).Style.Alignment.WrapText=true;
        sheet.Columns(1,cols).Width=23;sheet.SheetView.FreezeRows(HeaderRow);
        sheet.PageSetup.PageOrientation=XLPageOrientation.Landscape;sheet.PageSetup.FitToPages(1,0);
        return sheet;
    }
    private static void Headers(IXLWorksheet sheet,params string[] headers)
    {
        for(var i=0;i<headers.Length;i++) Text(sheet.Cell(HeaderRow,i+1),headers[i]);
        var range=sheet.Range(HeaderRow,1,HeaderRow,headers.Length);
        range.Style.Fill.BackgroundColor=Green;range.Style.Font.FontColor=XLColor.White;range.Style.Font.Bold=true;range.Style.Alignment.WrapText=true;sheet.Row(HeaderRow).Height=34;
    }
    private static void Row(IXLWorksheet sheet,int row,params object?[] values)
    {
        for(var i=0;i<values.Length;i++)
        {
            var cell=sheet.Cell(row,i+1);
            switch(values[i])
            {
                case decimal amount:cell.Value=(double)amount;cell.Style.NumberFormat.Format=MoneyFormat;break;
                case int number:cell.Value=number;cell.Style.NumberFormat.Format="#,##0";break;
                case long number:cell.Value=(double)number;cell.Style.NumberFormat.Format="#,##0";break;
                case DateTime date:cell.Value=date;cell.Style.NumberFormat.Format="dd/MM/yyyy HH:mm";break;
                default:Text(cell,values[i]?.ToString()??"");break;
            }
        }
    }
    private static void Text(IXLCell cell,string value)
    {
        // Assign a string value, never FormulaA1, hyperlinks or external references.
        cell.Value=value;cell.Style.NumberFormat.Format="@";
        if(value.TrimStart().StartsWith('=') || value.TrimStart().StartsWith('+') || value.TrimStart().StartsWith('-') || value.TrimStart().StartsWith('@')) cell.Style.IncludeQuotePrefix=true;
    }
    private static void Table(IXLWorksheet sheet,int end,int cols)
    {
        sheet.Range(HeaderRow,1,end,cols).SetAutoFilter();
        for(var row=8;row<=end;row++)
        {
            sheet.Row(row).Height=36;
            if(row%2==0) sheet.Range(row,1,row,cols).Style.Fill.BackgroundColor=Light;
        }
        var range=sheet.Range(8,1,end,cols);range.Style.Alignment.WrapText=true;
        range.Style.Border.BottomBorder=XLBorderStyleValues.Hair;range.Style.Border.BottomBorderColor=XLColor.FromHtml("#DCE7D6");
    }
    private static void TotalStyle(IXLWorksheet sheet,int row,int cols)
    {
        var range=sheet.Range(row,1,row,cols);range.Style.Font.Bold=true;range.Style.Fill.BackgroundColor=Light;sheet.Row(row).Height=30;
    }
    private static MemoryStream Save(XLWorkbook book,CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();book.Properties.Author="GreenShop";book.Properties.Title="GreenShop · Báo cáo Excel";
        var stream=new MemoryStream();
        try {book.SaveAs(stream);ct.ThrowIfCancellationRequested();stream.Position=0;return stream;}
        catch {stream.Dispose();throw;}
    }
}
