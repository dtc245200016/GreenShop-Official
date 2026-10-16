using GreenShop.Web.Services;
using Microsoft.AspNetCore.Mvc.Rendering;
using Microsoft.AspNetCore.Mvc.ViewFeatures;
using Microsoft.AspNetCore.Razor.TagHelpers;
using Microsoft.AspNetCore.WebUtilities;

namespace GreenShop.Web.TagHelpers;

// Carry the explicit Admin preview through local browsing without creating a cookie/session.
[HtmlTargetElement("a")]
[HtmlTargetElement("form")]
public class StorefrontPreviewTagHelper : TagHelper
{
    public override int Order => int.MaxValue;
    [ViewContext, HtmlAttributeNotBound]
    public ViewContext ViewContext { get; set; } = null!;

    public override void Process(TagHelperContext context, TagHelperOutput output)
    {
        var http=ViewContext.HttpContext;
        if(!http.User.IsInRole("Admin"))return;
        var attribute=output.TagName=="a" ? "href" : "action";
        var url=output.Attributes[attribute]?.Value?.ToString();
        if(string.IsNullOrEmpty(url) || !url.StartsWith('/') || url.StartsWith("//")
            || new PathString(url.Split('?', '#')[0]).StartsWithSegments("/Admin"))return;
        var fragment=url.IndexOf('#');
        var path=fragment<0 ? url : url[..fragment];
        // Our generated links have no portal parameter. Avoid duplicates in explicit links.
        if(!QueryHelpers.ParseQuery(path.Contains('?') ? path[(path.IndexOf('?')+1)..] : "")
            .ContainsKey(PortalAuthentication.PreviewParameter))
            output.Attributes.SetAttribute(attribute,QueryHelpers.AddQueryString(path,
                PortalAuthentication.PreviewParameter,"admin")+(fragment<0 ? "" : url[fragment..]));
        if(output.TagName=="form" && !string.Equals(output.Attributes["method"]?.Value?.ToString(),"post",StringComparison.OrdinalIgnoreCase))
            output.PostContent.AppendHtml("<input type=\"hidden\" name=\"portal\" value=\"admin\" />");
    }
}
