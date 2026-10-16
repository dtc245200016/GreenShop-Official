using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GreenShop.Web.Migrations
{
    /// <inheritdoc />
    public partial class AddReviewReplies : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<int>(
                name: "ReplyAdminId",
                table: "ProductReviews",
                type: "int",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ReplyContent",
                table: "ProductReviews",
                type: "varchar(1500)",
                maxLength: 1500,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<DateTime>(
                name: "ReplyCreatedAt",
                table: "ProductReviews",
                type: "datetime(6)",
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "ReplyUpdatedAt",
                table: "ProductReviews",
                type: "datetime(6)",
                nullable: true);

            migrationBuilder.CreateIndex(
                name: "IX_ProductReviews_ReplyAdminId",
                table: "ProductReviews",
                column: "ReplyAdminId");

            migrationBuilder.AddForeignKey(
                name: "FK_ProductReviews_Users_ReplyAdminId",
                table: "ProductReviews",
                column: "ReplyAdminId",
                principalTable: "Users",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_ProductReviews_Users_ReplyAdminId",
                table: "ProductReviews");

            migrationBuilder.DropIndex(
                name: "IX_ProductReviews_ReplyAdminId",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "ReplyAdminId",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "ReplyContent",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "ReplyCreatedAt",
                table: "ProductReviews");

            migrationBuilder.DropColumn(
                name: "ReplyUpdatedAt",
                table: "ProductReviews");
        }
    }
}
