using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GreenShop.Web.Migrations
{
    /// <inheritdoc />
    public partial class ReviewPerCompletedOrder : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_ProductReviews_UserId_CurrentProductId",
                table: "ProductReviews");

            migrationBuilder.CreateIndex(
                name: "IX_ProductReviews_UserId_CurrentProductId",
                table: "ProductReviews",
                columns: new[] { "UserId", "CurrentProductId" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // A rollback must fail before changing indexes if independent reviews
            // already exist. Never delete or merge customer reviews to restore uniqueness.
            migrationBuilder.CreateIndex(
                name: "IX_ProductReviews_ReviewRollbackUnique",
                table: "ProductReviews",
                columns: new[] { "UserId", "CurrentProductId" },
                unique: true);
            migrationBuilder.DropIndex(
                name: "IX_ProductReviews_UserId_CurrentProductId",
                table: "ProductReviews");
            migrationBuilder.RenameIndex(
                name: "IX_ProductReviews_ReviewRollbackUnique",
                table: "ProductReviews",
                newName: "IX_ProductReviews_UserId_CurrentProductId");
        }
    }
}
