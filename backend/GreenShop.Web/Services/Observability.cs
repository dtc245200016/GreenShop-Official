using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using Prometheus;

namespace GreenShop.Web.Services;

// No email, user ID, IP, raw URL, query string or authentication material is a label.
public sealed class Observability
{
    public static readonly Counter Failures = Metrics.CreateCounter("greenshop_auth_login_failures_total", "Rejected credential checks, excluding validation, throttling and account status.");
    private static readonly Counter Successes = Metrics.CreateCounter("greenshop_auth_login_successes_total", "Completed cookie sign-ins.");
    private static readonly Counter Denials = Metrics.CreateCounter("greenshop_auth_access_denied_total", "Authenticated access denied by cookie authorization or login portal role checks.");
    private static readonly Counter Requests = Metrics.CreateCounter("greenshop_http_requests_total", "Completed HTTP requests.", new CounterConfiguration { LabelNames = new[] { "route_group", "method", "status_code" } });
    private static readonly Histogram Duration = Metrics.CreateHistogram("greenshop_http_request_duration_seconds", "HTTP duration in seconds.", new HistogramConfiguration { LabelNames = new[] { "route_group" }, Buckets = new[] { .005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10 } });
    private static readonly Gauge Recent = Metrics.CreateGauge("greenshop_auth_login_failures_last_60s", "Exact in-process rolling count of actual rejected credential checks in the last 60 seconds; resets on process restart.");
    private readonly Queue<long> failureTimes = new();
    private readonly object gate = new();
    private readonly ILogger<Observability> logger;
    private readonly byte[]? expectedToken;

    public Observability(IConfiguration configuration, ILogger<Observability> logger)
    {
        this.logger = logger;
        var path = configuration["Metrics:TokenFile"];
        if (!string.IsNullOrEmpty(path))
        {
            var token = File.ReadAllText(path).Trim();
            if (token.Length < 32) throw new InvalidOperationException("Metrics token must contain at least 32 characters.");
            expectedToken = SHA256.HashData(Encoding.UTF8.GetBytes("Bearer " + token));
        }
        Failures.Inc(0); Successes.Inc(0); Denials.Inc(0); Recent.Set(0);
        Metrics.CreateGauge("greenshop_application_info", "GreenShop process is running.").Set(1);
        // Initialize status classes so an error panel shows zero before the first error.
        foreach(var status in new[]{"200","400","401","403","404","429","500","503"}) Requests.WithLabels("other","GET",status).Inc(0);
        Metrics.DefaultRegistry.AddBeforeCollectCallback(UpdateWindow);
    }

    public bool CanScrape(HttpContext context) => expectedToken != null &&
        CryptographicOperations.FixedTimeEquals(expectedToken, SHA256.HashData(Encoding.UTF8.GetBytes(context.Request.Headers.Authorization.ToString())));

    private void UpdateWindow()
    {
        lock (gate)
        {
            var now = Stopwatch.GetTimestamp();
            while (failureTimes.TryPeek(out var oldest) && Stopwatch.GetElapsedTime(oldest, now).TotalSeconds >= 60) failureTimes.Dequeue();
            Recent.Set(failureTimes.Count);
        }
    }

    public void LoginFailed(HttpContext context)
    {
        lock (gate)
        {
            var now=Stopwatch.GetTimestamp();
            while(failureTimes.TryPeek(out var oldest) && Stopwatch.GetElapsedTime(oldest,now).TotalSeconds>=60)failureTimes.Dequeue();
            // Existing rate limiter bounds events per process. Retain event times only, no identities.
            failureTimes.Enqueue(now);
            Failures.Inc();
        }
        SecurityEvent(context, "auth.login.failed", "invalid_credentials", LogLevel.Warning);
    }
    public void LoginSucceeded(HttpContext context) { Successes.Inc(); SecurityEvent(context, "auth.login.succeeded", "cookie_issued", LogLevel.Information); }
    public void AccessDenied(HttpContext context, string reason) { Denials.Inc(); SecurityEvent(context, "auth.access.denied", reason, LogLevel.Warning); }

    private void SecurityEvent(HttpContext context, string name, string reason, LogLevel level)
    {
        using var scope=logger.BeginScope(new Dictionary<string,object>{
            ["timestamp_utc"]=DateTimeOffset.UtcNow.ToString("O"), ["event"]=name,
            ["service"]="greenshop-web", ["request_id"]=context.TraceIdentifier,
            ["route"]=RouteGroup(context), ["reason_code"]=reason,
            ["actor_type"]=PortalAuthentication.IsAdmin(context.Request)?"admin_portal":"customer_portal",
            ["incident"]=name=="auth.login.failed"?"GS-SEC-001":"authentication" });
        logger.Log(level, new EventId(name=="auth.login.failed"?2001:name=="auth.login.succeeded"?2002:2003, name), "Security event {SecurityEvent}", name);
    }
    // Emit only after successful persistence/commit. No identifiers or customer data.
    public static void BusinessCreated(ILogger logger, HttpContext context, string name)
    {
        var id = name switch { "category.created" => 3001, "product.created" => 3002, "order.created" => 3003, _ => throw new ArgumentException("Unknown business event.", nameof(name)) };
        using var scope = logger.BeginScope(new Dictionary<string, object> {
            ["timestamp_utc"] = DateTimeOffset.UtcNow.ToString("O"), ["event"] = name,
            ["service"] = "greenshop-web", ["request_id"] = context.TraceIdentifier,
            ["route"] = RouteGroup(context), ["reason_code"] = "committed", ["incident"] = "business" });
        logger.LogInformation(new EventId(id, name), "Committed business event {BusinessEvent}", name);
    }
    public static string RouteGroup(HttpContext c)
    {
        var p=c.Request.Path;
        if(p.StartsWithSegments("/Admin"))return "admin";
        if(p.StartsWithSegments("/Account"))return "authentication";
        if(p.StartsWithSegments("/SanPham"))return "catalog";
        if(p.StartsWithSegments("/GioHang"))return "cart";
        if(p.StartsWithSegments("/ThanhToan"))return "orders";
        if(p.StartsWithSegments("/TuongTac"))return "engagement";
        if(p.StartsWithSegments("/supportHub")||p.StartsWithSegments("/TroLy"))return "support";
        if(p.StartsWithSegments("/health"))return "health";
        return p=="/"?"home":"other";
    }
    public static async Task Observe(HttpContext c, RequestDelegate next)
    {
        var start=Stopwatch.GetTimestamp();var group=RouteGroup(c);
        try { await next(c); }
        finally
        {
            var method=c.Request.Method is "GET" or "POST" or "PUT" or "DELETE" or "HEAD" or "OPTIONS" or "PATCH"?c.Request.Method:"OTHER";
            Requests.WithLabels(group,method,c.Response.StatusCode.ToString(System.Globalization.CultureInfo.InvariantCulture)).Inc();
            Duration.WithLabels(group).Observe(Stopwatch.GetElapsedTime(start).TotalSeconds);
        }
    }
}
