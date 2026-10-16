using System.ComponentModel.DataAnnotations;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using GreenShop.Web.Models;
using MySqlConnector;

namespace GreenShop.Web.Services;

// Operator-only CLI commands. No HTTP endpoint accepts bootstrap credentials.
internal static class DeploymentCommands
{
    public static async Task<bool> TryRunAsync(string[] args)
    {
        if(args.Length!=1 || args[0] is not ("--healthcheck" or "--bootstrap-db-user" or "--create-initial-admin"))return false;
        try
        {
            switch(args[0])
            {
                case "--healthcheck":
                    using(var client=new HttpClient{Timeout=TimeSpan.FromSeconds(4)})
                    using(var response=await client.GetAsync("http://127.0.0.1:8080/health/ready"))
                        Environment.ExitCode=response.IsSuccessStatusCode?0:1;
                    break;
                case "--bootstrap-db-user":await BootstrapDatabaseAsync();break;
                case "--create-initial-admin":await CreateAdminAsync();break;
            }
        }
        catch(Exception exception)
        {
            // CLI errors must not include connection strings, passwords or SQL parameters.
            Console.Error.WriteLine($"Deployment command failed ({exception.GetType().Name}). Check configuration/database access; existing accounts and passwords are preserved.");
            Environment.ExitCode=1;
        }
        return true;
    }

    private sealed record DatabaseInput(string Database,string RootPassword,string AppPassword);
    private static async Task BootstrapDatabaseAsync()
    {
        var input=await JsonSerializer.DeserializeAsync<DatabaseInput>(Console.OpenStandardInput()) ?? throw new ArgumentException("Missing input");
        if(!Regex.IsMatch(input.Database,@"\A[A-Za-z0-9_]{1,64}\z") || string.IsNullOrWhiteSpace(input.RootPassword)
            || !Regex.IsMatch(input.AppPassword,@"\A[A-Za-z0-9_-]{24,128}\z") || input.AppPassword.Contains("replace_",StringComparison.OrdinalIgnoreCase)
            || input.AppPassword==input.RootPassword)throw new ArgumentException("Use distinct generated secrets");
        var settings=new MySqlConnectionStringBuilder{Server="db",Database=input.Database,UserID="root",Password=input.RootPassword,Pooling=false,ConnectionTimeout=5,DefaultCommandTimeout=15};
        await using var root=new MySqlConnection(settings.ConnectionString);await root.OpenAsync();
        // MySQL schema grants escape '_' to avoid treating it as a wildcard.
        var grantSchema=input.Database.Replace("_","\\_");
        await using(var create=new MySqlCommand("CREATE USER IF NOT EXISTS 'greenshop_app'@'%' IDENTIFIED BY @password",root))
        {create.Parameters.AddWithValue("@password",input.AppPassword);await create.ExecuteNonQueryAsync();}
        // Never silently change the password or broaden privileges of an existing account.
        await using(var grants=new MySqlCommand("SHOW GRANTS FOR 'greenshop_app'@'%'",root))
        await using(var reader=await grants.ExecuteReaderAsync())
            while(await reader.ReadAsync())
            {
                var grant=reader.GetString(0).Replace("\\_","_");
                if((!grant.StartsWith("GRANT USAGE ON *.*",StringComparison.OrdinalIgnoreCase)
                    && !grant.Contains($" ON `{input.Database}`.* TO ",StringComparison.OrdinalIgnoreCase))
                    || grant.Contains("WITH GRANT OPTION",StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Unexpected existing grants");
            }
        settings.UserID="greenshop_app";settings.Password=input.AppPassword;settings.Database="";
        await using(var verify=new MySqlConnection(settings.ConnectionString))await verify.OpenAsync();
        await using(var grant=new MySqlCommand($"GRANT ALL PRIVILEGES ON `{grantSchema}`.* TO 'greenshop_app'@'%'",root))await grant.ExecuteNonQueryAsync();
        Console.WriteLine("Database application account verified; privileges are limited to its schema, including DDL required by startup migrations. Root password unchanged.");
    }

    private sealed record AdminInput(string FullName,string Email,string Password);
    private static async Task CreateAdminAsync()
    {
        var input=await JsonSerializer.DeserializeAsync<AdminInput>(Console.OpenStandardInput()) ?? throw new ArgumentException("Missing input");
        var model=new RegisterViewModel{FullName=input.FullName.Trim(),Email=input.Email.Trim().ToLowerInvariant(),Password=input.Password,ConfirmPassword=input.Password};
        if(!ShopOwnership.IsOwnerEmail(model.Email))throw new ArgumentException("Initial Admin must use the reserved shop-owner email: "+ShopOwnership.OwnerEmail);
        if(!Validator.TryValidateObject(model,new ValidationContext(model),null,true) || input.Password.Length<12 || Encoding.UTF8.GetByteCount(input.Password)>72)
            throw new ArgumentException("Invalid administrator fields");
        var connectionString=Environment.GetEnvironmentVariable("ConnectionStrings__DefaultConnection") ?? throw new InvalidOperationException("Missing database configuration");
        var settings=new MySqlConnectionStringBuilder(connectionString){Pooling=false,ConnectionTimeout=5,DefaultCommandTimeout=15};
        await using var db=new MySqlConnection(settings.ConnectionString);await db.OpenAsync();
        await using(var acquire=new MySqlCommand("SELECT GET_LOCK(@lockName,10)",db))
        {
            acquire.Parameters.AddWithValue("@lockName","gs_init_"+Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(settings.Database)))[..24]);
            if(Convert.ToInt32(await acquire.ExecuteScalarAsync())!=1)throw new InvalidOperationException("Bootstrap already in progress");
        }
        // Closing this dedicated connection releases the advisory lock, including on failure.
        await using(var count=new MySqlCommand("SELECT COUNT(*) FROM Users",db))
            if(Convert.ToInt64(await count.ExecuteScalarAsync())!=0)
            {
                Console.Error.WriteLine("Initial Admin creation is allowed only when Users is empty. Use the existing accounts; no role/password was changed.");Environment.ExitCode=1;return;
            }
        await using var insert=new MySqlCommand("INSERT INTO Users (FullName,Email,PasswordHash,Phone,Role,CreatedAt,IsActive,Version,SessionVersion) VALUES (@name,@email,@hash,'',1,UTC_TIMESTAMP(6),1,0,0)",db);
        insert.Parameters.AddWithValue("@name",model.FullName);insert.Parameters.AddWithValue("@email",model.Email);insert.Parameters.AddWithValue("@hash",BCrypt.Net.BCrypt.HashPassword(input.Password));
        await insert.ExecuteNonQueryAsync();Console.WriteLine("Initial Admin created. No default password is supplied or stored in source.");
    }
}
