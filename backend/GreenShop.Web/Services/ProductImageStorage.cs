using System.Buffers.Binary;
using System.Text.RegularExpressions;

namespace GreenShop.Web.Services;

// Chỉ quản lý các ảnh do chức năng Products tạo; không nhận đường dẫn vật lý từ form.
internal sealed class ProductImageStorage
{
    public const long MaxFileSize = 5 * 1024 * 1024;
    private const string UrlPrefix = "/uploads/products/";
    private readonly string _directory;
    private readonly ILogger _logger;

    public ProductImageStorage(IWebHostEnvironment environment, ILogger logger)
    {
        _directory = Path.Combine(environment.WebRootPath, "uploads", "products");
        _logger = logger;
    }

    public async Task<string?> ValidateAsync(IFormFile file, CancellationToken cancellationToken)
    {
        if (file.Length == 0) return "Ảnh không được là file rỗng.";
        if (file.Length > MaxFileSize) return "Ảnh không được vượt quá 5 MiB.";
        if (string.IsNullOrWhiteSpace(file.FileName) || file.FileName.IndexOfAny(new[] { '/', '\\', '\0' }) >= 0)
            return "Tên file ảnh không hợp lệ.";

        var extension = Path.GetExtension(file.FileName).ToLowerInvariant();
        if (extension is not (".jpg" or ".jpeg" or ".png" or ".webp"))
            return "Chỉ chấp nhận ảnh JPG, JPEG, PNG hoặc WebP.";

        await using var stream = file.OpenReadStream();
        var header = new byte[12];
        var count = await stream.ReadAtLeastAsync(header.AsMemory(), 12, false, cancellationToken);
        var valid = count == 12 && (extension switch
        {
            ".jpg" or ".jpeg" => header[0] == 0xff && header[1] == 0xd8 && header[2] == 0xff,
            ".png" => header.AsSpan(0, 8).SequenceEqual(new byte[] { 137, 80, 78, 71, 13, 10, 26, 10 }),
            ".webp" => header.AsSpan(0, 4).SequenceEqual("RIFF"u8)
                && header.AsSpan(8, 4).SequenceEqual("WEBP"u8)
                && BinaryPrimitives.ReadUInt32LittleEndian(header.AsSpan(4, 4)) == file.Length - 8,
            _ => false
        });
        return valid ? null : "Nội dung ảnh không khớp định dạng file đã chọn.";
    }

    public async Task<string> SaveAsync(IFormFile file, CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(_directory);
        var extension = Path.GetExtension(file.FileName).ToLowerInvariant();
        if (extension == ".jpeg") extension = ".jpg";
        var name = Guid.NewGuid().ToString("N") + extension;
        var url = UrlPrefix + name;
        var created = false;
        try
        {
            await using var output = new FileStream(Path.Combine(_directory, name), FileMode.CreateNew,
                FileAccess.Write, FileShare.None, 81920, FileOptions.Asynchronous);
            created = true;
            await file.CopyToAsync(output, cancellationToken);
            return url;
        }
        catch
        {
            if (created) Delete(url);
            throw;
        }
    }

    public bool Delete(string url)
    {
        if (!Regex.IsMatch(url, "\\A/uploads/products/[a-f0-9]{32}\\.(jpg|png|webp)\\z"))
            return true;

        try
        {
            File.Delete(Path.Combine(_directory, url[UrlPrefix.Length..]));
            return true;
        }
        catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
        {
            _logger.LogWarning(exception, "Không thể dọn một ảnh sản phẩm đã quản lý.");
            return false;
        }
    }
}
