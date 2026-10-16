using System;
using Microsoft.EntityFrameworkCore.Metadata;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GreenShop.Web.Migrations
{
    /// <inheritdoc />
    public partial class CompleteCustomerEngagement : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "AssignedAdminId",
                table: "ShopConversations",
                type: "int",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Status",
                table: "ShopConversations",
                type: "varchar(20)",
                maxLength: 20,
                nullable: false,
                defaultValue: "Waiting")
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<long>(
                name: "Version",
                table: "ShopConversations",
                type: "bigint",
                nullable: false,
                defaultValue: 0L);

            migrationBuilder.AddColumn<string>(
                name: "Image4",
                table: "ProductReviews",
                type: "varchar(255)",
                maxLength: 255,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<string>(
                name: "Image5",
                table: "ProductReviews",
                type: "varchar(255)",
                maxLength: 255,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<bool>(
                name: "IsCurrent",
                table: "ProductReviews",
                type: "tinyint(1)",
                nullable: false,
                defaultValue: true);

            migrationBuilder.AddColumn<bool>(
                name: "IsHidden",
                table: "ProductReviews",
                type: "tinyint(1)",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<DateTime>(
                name: "UpdatedAt",
                table: "ProductReviews",
                type: "datetime(6)",
                nullable: true);

            migrationBuilder.AddColumn<long>(
                name: "Version",
                table: "ProductReviews",
                type: "bigint",
                nullable: false,
                defaultValue: 0L);

            migrationBuilder.AddColumn<int>(
                name: "CurrentProductId",
                table: "ProductReviews",
                type: "int",
                nullable: true,
                computedColumnSql: "CASE WHEN `IsCurrent` = 1 THEN `ProductId` ELSE NULL END",
                stored: false);

            migrationBuilder.CreateTable(
                name: "AdminNotifications",
                columns: table => new
                {
                    Id = table.Column<long>(type: "bigint", nullable: false)
                        .Annotation("MySql:ValueGenerationStrategy", MySqlValueGenerationStrategy.IdentityColumn),
                    RecipientId = table.Column<int>(type: "int", nullable: false),
                    EventKey = table.Column<string>(type: "varchar(100)", maxLength: 100, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    Kind = table.Column<string>(type: "varchar(20)", maxLength: 20, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    Title = table.Column<string>(type: "varchar(150)", maxLength: 150, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    Link = table.Column<string>(type: "varchar(255)", maxLength: 255, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    CreatedAt = table.Column<DateTime>(type: "datetime(6)", nullable: false),
                    ReadAt = table.Column<DateTime>(type: "datetime(6)", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AdminNotifications", x => x.Id);
                    table.ForeignKey(
                        name: "FK_AdminNotifications_Users_RecipientId",
                        column: x => x.RecipientId,
                        principalTable: "Users",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                })
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.CreateTable(
                name: "ShopConversationReads",
                columns: table => new
                {
                    ConversationId = table.Column<int>(type: "int", nullable: false),
                    AdminId = table.Column<int>(type: "int", nullable: false),
                    ThroughMessageId = table.Column<long>(type: "bigint", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ShopConversationReads", x => new { x.ConversationId, x.AdminId });
                    table.ForeignKey(
                        name: "FK_ShopConversationReads_ShopConversations_ConversationId",
                        column: x => x.ConversationId,
                        principalTable: "ShopConversations",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_ShopConversationReads_Users_AdminId",
                        column: x => x.AdminId,
                        principalTable: "Users",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                })
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.CreateIndex(
                name: "IX_ShopConversations_AssignedAdminId",
                table: "ShopConversations",
                column: "AssignedAdminId");

            migrationBuilder.AddCheckConstraint(
                name: "CK_ShopConversations_Status",
                table: "ShopConversations",
                sql: "`Status` IN ('Waiting','InProgress','Resolved')");

            // Keep every historical row and image. For duplicate Customer/Product pairs,
            // select the latest CreatedAt/Id as current before adding uniqueness.
            migrationBuilder.Sql(@"UPDATE ProductReviews oldReview
                JOIN ProductReviews newer ON newer.UserId=oldReview.UserId AND newer.ProductId=oldReview.ProductId
                  AND (newer.CreatedAt>oldReview.CreatedAt OR (newer.CreatedAt=oldReview.CreatedAt AND newer.Id>oldReview.Id))
                SET oldReview.IsCurrent=0 WHERE oldReview.ProductId IS NOT NULL;");

            migrationBuilder.CreateIndex(
                name: "IX_ProductReviews_UserId_CurrentProductId",
                table: "ProductReviews",
                columns: new[] { "UserId", "CurrentProductId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_AdminNotifications_RecipientId_EventKey",
                table: "AdminNotifications",
                columns: new[] { "RecipientId", "EventKey" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_AdminNotifications_RecipientId_ReadAt_Id",
                table: "AdminNotifications",
                columns: new[] { "RecipientId", "ReadAt", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_ShopConversationReads_AdminId",
                table: "ShopConversationReads",
                column: "AdminId");

            migrationBuilder.AddForeignKey(
                name: "FK_ShopConversations_Users_AssignedAdminId",
                table: "ShopConversations",
                column: "AssignedAdminId",
                principalTable: "Users",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_ShopConversations_Users_AssignedAdminId",
                table: "ShopConversations");

            migrationBuilder.DropTable(
                name: "AdminNotifications");

            migrationBuilder.DropTable(
                name: "ShopConversationReads");

            migrationBuilder.DropIndex(
                name: "IX_ShopConversations_AssignedAdminId",
                table: "ShopConversations");

            migrationBuilder.DropCheckConstraint(
                name: "CK_ShopConversations_Status",
                table: "ShopConversations");

            migrationBuilder.DropIndex(
                name: "IX_ProductReviews_UserId_CurrentProductId",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "CurrentProductId",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "AssignedAdminId",
                table: "ShopConversations");

            migrationBuilder.DropColumn(
                name: "Status",
                table: "ShopConversations");

            migrationBuilder.DropColumn(
                name: "Version",
                table: "ShopConversations");

            migrationBuilder.DropColumn(
                name: "Image4",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "Image5",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "IsCurrent",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "IsHidden",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "UpdatedAt",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "Version",
                table: "ProductReviews");

        }
    }
}
