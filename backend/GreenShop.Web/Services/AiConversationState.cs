using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Options;

namespace GreenShop.Web.Services;

// Encrypted, authenticated history is browser/account bound. No anonymous MySQL storage.
public sealed class AiConversationState(IDataProtectionProvider protection,IOptions<AiChatOptions> options)
{
    public const int MaximumTokenLength=65536;
    private record State(DateTimeOffset Expires,IReadOnlyList<AiTurn> Turns);
    private IDataProtector Protector(string binding)=>protection.CreateProtector("GreenShop.AiHistory.v1",binding);
    public IReadOnlyList<AiTurn>? Read(string? token,string binding)
    {
        if(string.IsNullOrEmpty(token)) return [];
        if(token.Length>MaximumTokenLength) return null;
        try {
            var state=JsonSerializer.Deserialize<State>(Protector(binding).Unprotect(token));
            return state!=null && state.Expires>DateTimeOffset.UtcNow && ValidTurns(state.Turns,false)?Trim(state.Turns):null;
        } catch(Exception ex) when(ex is CryptographicException or JsonException or FormatException) {return null;}
    }
    public string Write(IReadOnlyList<AiTurn> turns,string binding)=>Protector(binding).Protect(
        JsonSerializer.Serialize(new State(DateTimeOffset.UtcNow.AddMinutes(30),Trim(turns))));
    private IReadOnlyList<AiTurn> Trim(IReadOnlyList<AiTurn> turns) {
        var result=turns.TakeLast(2*Math.Clamp(options.Value.HistoryTurns,1,4)).ToArray();
        while(result.Sum(t=>t.Text.Length)>6000 && result.Length>2) result=result.Skip(2).ToArray();
        return result;
    }
    public static bool ValidTurns(IReadOnlyList<AiTurn>? turns,bool includeQuestion)
    {
        if(turns==null || turns.Count>(includeQuestion?9:8) || turns.Count%2!=(includeQuestion?1:0)) return false;
        for(var i=0;i<turns.Count;i++) {
            var t=turns[i];if(t==null || t.Role!=(i%2==0?"user":"assistant") || string.IsNullOrWhiteSpace(t.Text)
                || t.Text.Length>(i%2==0?1000:2000)) return false;
        }
        return true;
    }
}
