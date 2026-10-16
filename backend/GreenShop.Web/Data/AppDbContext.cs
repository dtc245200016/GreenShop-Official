
using Microsoft.EntityFrameworkCore;
using GreenShop.Web.Models;

namespace GreenShop.Web.Data
{
    public class AppDbContext : DbContext
    {
        public AppDbContext(
            DbContextOptions<AppDbContext> options
        ) : base(options)
        {
        }

        public DbSet<User> Users { get; set; } = null!;
        public DbSet<Product> Products { get; set; } = null!;
        public DbSet<Category> Categories { get; set; } = null!;
        public DbSet<CartItem> CartItems { get; set; } = null!;
        public DbSet<Order> Orders { get; set; } = null!;
        public DbSet<OrderItem> OrderItems { get; set; } = null!;
        public DbSet<OrderStatusHistory> OrderStatusHistories { get; set; } = null!;
        public DbSet<PaymentShippingSettings> PaymentShippingSettings { get; set; } = null!;
        public DbSet<HomeSliderSettings> HomeSliderSettings { get; set; } = null!;
        public DbSet<ProductReview> ProductReviews { get; set; } = null!;
        public DbSet<ShopConversation> ShopConversations { get; set; } = null!;
        public DbSet<ShopMessage> ShopMessages { get; set; } = null!;

        public DbSet<AdminNotification> AdminNotifications { get; set; } = null!;
        public DbSet<ShopConversationRead> ShopConversationReads { get; set; } = null!;

        protected override void OnModelCreating(
            ModelBuilder modelBuilder)
        {
            base.OnModelCreating(modelBuilder);

            modelBuilder.Entity<HomeSliderSettings>(e => {
                e.Property(s=>s.Id).ValueGeneratedNever();e.Property(s=>s.Mode).HasMaxLength(20);
                e.Property(s=>s.Version).IsConcurrencyToken();
                e.ToTable(t=>t.HasCheckConstraint("CK_HomeSliderSettings", "`Id` = 1 AND `ProductCount` BETWEEN 1 AND 100 AND `Days` BETWEEN 0 AND 3650 AND `Mode` IN ('all','bestsellers')"));
                e.HasData(new HomeSliderSettings {Id=1,Mode="bestsellers",ProductCount=5,Days=30,Version=0});
            });
            modelBuilder.Entity<ProductReview>(e=> {
                e.Property(r=>r.IsCurrent).HasDefaultValue(true);
                e.Property(r=>r.CurrentProductId).HasComputedColumnSql("CASE WHEN `IsCurrent` = 1 THEN `ProductId` ELSE NULL END", stored:false);
                e.Property(r=>r.Version).IsConcurrencyToken();
                e.HasIndex(r=>new {r.UserId,r.CurrentProductId});e.HasIndex(r=>r.UserId);
                e.HasIndex(r=>r.OrderItemId).IsUnique();e.HasIndex(r=>new {r.ProductId,r.CreatedAt});e.HasIndex(r=>r.AdminReadAt);
                e.HasOne(r=>r.OrderItem).WithMany().HasForeignKey(r=>r.OrderItemId).OnDelete(DeleteBehavior.Restrict);
                e.HasOne(r=>r.User).WithMany().HasForeignKey(r=>r.UserId).OnDelete(DeleteBehavior.Restrict);
                e.HasOne(r=>r.Product).WithMany().HasForeignKey(r=>r.ProductId).OnDelete(DeleteBehavior.SetNull);
                e.HasOne<User>().WithMany().HasForeignKey(r=>r.ReplyAdminId).OnDelete(DeleteBehavior.Restrict);
                e.ToTable(t=>t.HasCheckConstraint("CK_ProductReviews_Stars","`Stars` BETWEEN 1 AND 5"));
            });
            modelBuilder.Entity<ShopConversation>(e=> {
                e.Property(c=>c.Status).HasDefaultValue("Waiting");e.Property(c=>c.Version).IsConcurrencyToken();
                e.HasOne(c=>c.AssignedAdmin).WithMany().HasForeignKey(c=>c.AssignedAdminId).OnDelete(DeleteBehavior.Restrict);
                e.ToTable(t=>t.HasCheckConstraint("CK_ShopConversations_Status", "`Status` IN ('Waiting','InProgress','Resolved')"));
                e.HasIndex(c=>c.CustomerId).IsUnique();e.HasIndex(c=>c.UpdatedAt);
                e.HasOne(c=>c.Customer).WithMany().HasForeignKey(c=>c.CustomerId).OnDelete(DeleteBehavior.Restrict);
            });
            modelBuilder.Entity<ShopMessage>(e=> {
                e.HasIndex(m=>new {m.SenderId,m.RequestToken}).IsUnique();e.HasIndex(m=>new {m.ConversationId,m.Id});e.HasIndex(m=>new {m.SenderId,m.CreatedAt});
                e.HasOne(m=>m.Conversation).WithMany().HasForeignKey(m=>m.ConversationId).OnDelete(DeleteBehavior.Restrict);
                e.HasOne(m=>m.Sender).WithMany().HasForeignKey(m=>m.SenderId).OnDelete(DeleteBehavior.Restrict);
            });

            modelBuilder.Entity<AdminNotification>(e=> {
                e.HasIndex(n=>new {n.RecipientId,n.EventKey}).IsUnique();e.HasIndex(n=>new {n.RecipientId,n.ReadAt,n.Id});
                e.HasOne(n=>n.Recipient).WithMany().HasForeignKey(n=>n.RecipientId).OnDelete(DeleteBehavior.Restrict);
            });
            modelBuilder.Entity<ShopConversationRead>(e=> {
                e.HasKey(r=>new {r.ConversationId,r.AdminId});
                e.HasOne(r=>r.Conversation).WithMany().HasForeignKey(r=>r.ConversationId).OnDelete(DeleteBehavior.Restrict);
                e.HasOne(r=>r.Admin).WithMany().HasForeignKey(r=>r.AdminId).OnDelete(DeleteBehavior.Restrict);
            });

            modelBuilder.Entity<User>()
                .HasIndex(u => u.Email)
                .IsUnique();
            modelBuilder.Entity<User>().Property(u => u.IsActive).HasDefaultValue(true);
            modelBuilder.Entity<User>().Property(u => u.Version).IsConcurrencyToken();
            modelBuilder.Entity<User>().HasIndex(u => new { u.Role, u.IsActive });

            modelBuilder.Entity<Product>(entity =>
            {
                entity.ToTable("Products");

                entity.Property(p => p.Name)
                    .HasMaxLength(150)
                    .IsRequired();

                entity.Property(p => p.Price)
                    .HasColumnType("decimal(18,2)");

                entity.Property(p => p.ImageUrl)
                    .HasMaxLength(255)
                    .IsRequired();

                entity.Property(p => p.Description)
                    .HasMaxLength(2000)
                    .IsRequired();

                entity.HasOne(p => p.Category)
                    .WithMany(c => c.Products)
                    .HasForeignKey(p => p.CategoryId)
                    .OnDelete(DeleteBehavior.Restrict);
            });

            modelBuilder.Entity<Category>(entity =>
            {
                entity.ToTable("Categories");
                entity.Property(c => c.Name)
                    .HasMaxLength(100)
                    .UseCollation("utf8mb4_0900_as_ci")
                    .IsRequired();
                entity.Property(c => c.Description).HasMaxLength(500).IsRequired();
                entity.HasIndex(c => c.Name).IsUnique();
            });

            modelBuilder.Entity<CartItem>(entity =>
            {
                entity.HasIndex(i => new { i.UserId, i.ProductId }).IsUnique();
                entity.HasOne(i => i.User).WithMany().HasForeignKey(i => i.UserId).OnDelete(DeleteBehavior.Restrict);
                entity.HasOne(i => i.Product).WithMany().HasForeignKey(i => i.ProductId).OnDelete(DeleteBehavior.Cascade);
                entity.ToTable(t => t.HasCheckConstraint("CK_CartItems_Quantity", "`Quantity` > 0"));
            });
            modelBuilder.Entity<Order>(entity =>
            {
                entity.Property(o => o.ConfirmationToken).HasMaxLength(32).IsRequired();
                entity.HasIndex(o => new { o.UserId, o.ConfirmationToken }).IsUnique();
                entity.Property(o => o.RecipientName).HasMaxLength(100).IsRequired();
                entity.Property(o => o.Phone).HasMaxLength(21).IsRequired();
                entity.Property(o => o.Address).HasMaxLength(500).IsRequired();
                entity.Property(o => o.PaymentMethod).HasMaxLength(10).IsRequired();
                entity.Property(o => o.Total).HasPrecision(18, 2);
                entity.Property(o=>o.Subtotal).HasPrecision(18,2);
                entity.Property(o=>o.ShippingFee).HasPrecision(18,2);
                entity.Property(o=>o.ShippingFlatFeeSnapshot).HasPrecision(18,2);
                entity.Property(o=>o.FreeShippingThresholdSnapshot).HasPrecision(18,2);
                entity.Property(o=>o.BankBinSnapshot).HasMaxLength(6);
                entity.Property(o=>o.BankNameSnapshot).HasMaxLength(200);
                entity.Property(o=>o.BankAccountSnapshot).HasMaxLength(19);
                entity.Property(o=>o.BankHolderSnapshot).HasMaxLength(100);
                entity.Property(o=>o.TransferContent).HasMaxLength(50);
                entity.Property(o=>o.PaymentConfirmedByName).HasMaxLength(100);
                entity.HasIndex(o=>o.TransferContent).IsUnique();
                entity.HasOne(o=>o.PaymentConfirmedBy).WithMany().HasForeignKey(o=>o.PaymentConfirmedById).OnDelete(DeleteBehavior.Restrict);
                entity.Property(o => o.AdminNote).HasMaxLength(1000).IsRequired();
                entity.Property(o => o.Version).IsConcurrencyToken();
                entity.HasIndex(o => new { o.Status, o.CreatedAt });
                entity.HasIndex(o => o.CreatedAt);
                entity.HasOne(o => o.User).WithMany().HasForeignKey(o => o.UserId).OnDelete(DeleteBehavior.Restrict);
                entity.HasIndex(o => new { o.UserId, o.CreatedAt });
            });
            modelBuilder.Entity<OrderItem>(entity =>
            {
                entity.Property(i => i.ProductName).HasMaxLength(150).IsRequired();
                entity.Property(i => i.ImageUrl).HasMaxLength(255).IsRequired();
                entity.Property(i => i.UnitPrice).HasPrecision(18, 2);
                entity.HasOne(i => i.Order).WithMany(o => o.Items).HasForeignKey(i => i.OrderId).OnDelete(DeleteBehavior.Cascade);
                entity.HasOne(i => i.Product).WithMany().HasForeignKey(i => i.ProductId).OnDelete(DeleteBehavior.SetNull);
                entity.ToTable(t => t.HasCheckConstraint("CK_OrderItems_Quantity", "`Quantity` > 0"));
            });
            modelBuilder.Entity<OrderStatusHistory>(entity =>
            {
                entity.Property(h => h.AdminName).HasMaxLength(100).IsRequired();
                entity.Property(h => h.Note).HasMaxLength(1000).IsRequired();
                entity.HasOne(h => h.Order).WithMany(o => o.History).HasForeignKey(h => h.OrderId).OnDelete(DeleteBehavior.Restrict);
                entity.HasOne(h => h.Admin).WithMany().HasForeignKey(h => h.AdminId).OnDelete(DeleteBehavior.SetNull);
                entity.HasIndex(h => new { h.OrderId, h.CreatedAt });
            });
            modelBuilder.Entity<PaymentShippingSettings>(entity=>
            {
                entity.Property(s=>s.Id).ValueGeneratedNever();
                entity.Property(s=>s.BankBin).HasMaxLength(6).IsRequired();
                entity.Property(s=>s.BankName).HasMaxLength(200).IsRequired();
                entity.Property(s=>s.AccountNumber).HasMaxLength(19).IsRequired();
                entity.Property(s=>s.AccountHolderName).HasMaxLength(100).IsRequired();
                entity.Property(s=>s.FlatShippingFee).HasPrecision(18,2);
                entity.Property(s=>s.FreeShippingThreshold).HasPrecision(18,2);
                entity.Property(s=>s.Version).IsConcurrencyToken();
                entity.ToTable(t=>t.HasCheckConstraint("CK_PaymentShippingSettings_Singleton","`Id` = 1"));
            });
        }
    }
}
