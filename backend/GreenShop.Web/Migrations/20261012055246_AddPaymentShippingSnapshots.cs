using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace GreenShop.Web.Migrations
{
    /// <inheritdoc />
    public partial class AddPaymentShippingSnapshots : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "BankAccountSnapshot",
                table: "Orders",
                type: "varchar(19)",
                maxLength: 19,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<string>(
                name: "BankBinSnapshot",
                table: "Orders",
                type: "varchar(6)",
                maxLength: 6,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<string>(
                name: "BankHolderSnapshot",
                table: "Orders",
                type: "varchar(100)",
                maxLength: 100,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<string>(
                name: "BankNameSnapshot",
                table: "Orders",
                type: "varchar(200)",
                maxLength: 200,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<DateTime>(
                name: "CustomerTransferNotifiedAt",
                table: "Orders",
                type: "datetime(6)",
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "FreeShippingThresholdSnapshot",
                table: "Orders",
                type: "decimal(18,2)",
                precision: 18,
                scale: 2,
                nullable: true);

            migrationBuilder.AddColumn<DateTime>(
                name: "PaidAt",
                table: "Orders",
                type: "datetime(6)",
                nullable: true);

            migrationBuilder.AddColumn<int>(
                name: "PaymentConfirmedById",
                table: "Orders",
                type: "int",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "PaymentConfirmedByName",
                table: "Orders",
                type: "varchar(100)",
                maxLength: 100,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.AddColumn<decimal>(
                name: "ShippingFee",
                table: "Orders",
                type: "decimal(18,2)",
                precision: 18,
                scale: 2,
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "ShippingFlatFeeSnapshot",
                table: "Orders",
                type: "decimal(18,2)",
                precision: 18,
                scale: 2,
                nullable: true);

            migrationBuilder.AddColumn<decimal>(
                name: "Subtotal",
                table: "Orders",
                type: "decimal(18,2)",
                precision: 18,
                scale: 2,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "TransferContent",
                table: "Orders",
                type: "varchar(50)",
                maxLength: 50,
                nullable: true)
                .Annotation("MySql:CharSet", "utf8mb4");

            migrationBuilder.CreateTable(
                name: "PaymentShippingSettings",
                columns: table => new
                {
                    Id = table.Column<int>(type: "int", nullable: false),
                    BankBin = table.Column<string>(type: "varchar(6)", maxLength: 6, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    BankName = table.Column<string>(type: "varchar(200)", maxLength: 200, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    AccountNumber = table.Column<string>(type: "varchar(19)", maxLength: 19, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    AccountHolderName = table.Column<string>(type: "varchar(100)", maxLength: 100, nullable: false)
                        .Annotation("MySql:CharSet", "utf8mb4"),
                    VietQrEnabled = table.Column<bool>(type: "tinyint(1)", nullable: false),
                    FlatShippingFee = table.Column<decimal>(type: "decimal(18,2)", precision: 18, scale: 2, nullable: false),
                    FreeShippingThreshold = table.Column<decimal>(type: "decimal(18,2)", precision: 18, scale: 2, nullable: false),
                    Version = table.Column<long>(type: "bigint", nullable: false),
                    UpdatedAt = table.Column<DateTime>(type: "datetime(6)", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_PaymentShippingSettings", x => x.Id);
                    table.CheckConstraint("CK_PaymentShippingSettings_Singleton", "`Id` = 1");
                })
                .Annotation("MySql:CharSet", "utf8mb4");

            // Only seed the new singleton settings. Historical orders remain untouched/null.
            migrationBuilder.InsertData(
                table: "PaymentShippingSettings",
                columns: new[] { "Id", "BankBin", "BankName", "AccountNumber", "AccountHolderName", "VietQrEnabled", "FlatShippingFee", "FreeShippingThreshold", "Version" },
                values: new object[] { 1, "", "", "", "", false, 30000m, 300000m, 0L });

            migrationBuilder.CreateIndex(
                name: "IX_Orders_PaymentConfirmedById",
                table: "Orders",
                column: "PaymentConfirmedById");

            migrationBuilder.CreateIndex(
                name: "IX_Orders_TransferContent",
                table: "Orders",
                column: "TransferContent",
                unique: true);

            migrationBuilder.AddForeignKey(
                name: "FK_Orders_Users_PaymentConfirmedById",
                table: "Orders",
                column: "PaymentConfirmedById",
                principalTable: "Users",
                principalColumn: "Id",
                onDelete: ReferentialAction.Restrict);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropForeignKey(
                name: "FK_Orders_Users_PaymentConfirmedById",
                table: "Orders");

            migrationBuilder.DropTable(
                name: "PaymentShippingSettings");

            migrationBuilder.DropIndex(
                name: "IX_Orders_PaymentConfirmedById",
                table: "Orders");

            migrationBuilder.DropIndex(
                name: "IX_Orders_TransferContent",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "BankAccountSnapshot",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "BankBinSnapshot",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "BankHolderSnapshot",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "BankNameSnapshot",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "CustomerTransferNotifiedAt",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "FreeShippingThresholdSnapshot",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "PaidAt",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "PaymentConfirmedById",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "PaymentConfirmedByName",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "ShippingFee",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "ShippingFlatFeeSnapshot",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "Subtotal",
                table: "Orders");

            migrationBuilder.DropColumn(
                name: "TransferContent",
                table: "Orders");
        }
    }
}
