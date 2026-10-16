
using System.ComponentModel.DataAnnotations;

namespace GreenShop.Web.Models
{
    public class Product
    {
        public int Id { get; set; }

        [Required, StringLength(150)]
        public string Name { get; set; } = string.Empty;

        [Range(typeof(decimal), "0.01", "9999999999.99")]
        public decimal Price { get; set; }

        [Required, StringLength(255)]
        public string ImageUrl { get; set; } = string.Empty;

        [StringLength(2000)]
        public string Description { get; set; } = string.Empty;

        [Range(0, int.MaxValue)]
        public int StockQuantity { get; set; }

        public int? CategoryId { get; set; }

        public Category? Category { get; set; }
    }
}
