import Foundation

/// One draft line of a recording in progress, as `transcript_previews` hands it back. A draft is never a Row:
/// it does not enter `rows`, blocks, search, the summary or naming — the final pass alone writes the transcript.
struct PreviewDraft:Identifiable, Equatable {
    let id:String; let source:String; let epoch:Int; let revision:Int; let status:String; let text:String
    let start:Double; let end:Double; let updated:Double
    init(_ d:[String:Any]) {
        id=d["span_id"] as? String ?? ""; source=d["source"] as? String ?? ""; epoch=d["epoch"] as? Int ?? 1; revision=d["revision"] as? Int ?? 1
        status=d["status"] as? String ?? ""; text=(d["text"] as? String ?? "").trimmingCharacters(in:.whitespacesAndNewlines)
        start=PreviewDrafts.number(d["audio_start"]) ?? 0; end=PreviewDrafts.number(d["audio_end"]) ?? start; updated=PreviewDrafts.number(d["updated"]) ?? 0
    }
    var time:String { String(format:"%02d:%02d",Int(start)/60,Int(start)%60) }
    var sourceLabel:String { source=="mic" ? "Mikrofon" : (source=="system" ? "Sistem sesi" : "Ses") }
    /// "partial" may still change under the same span; a draft "final" is only final for the draft — the
    /// meeting's own transcript still comes from the pass that runs after the recording.
    var label:String { status=="partial" ? "Taslak · değişebilir" : "Taslak" }
    var hasText:Bool { !text.isEmpty && (status=="partial" || status=="final") }
}

/// The worker's session row: running, paused (a budget or the network), stopped or disabled.
struct PreviewSession:Equatable {
    let state:String; let reason:String; let lagSeconds:Double; let epoch:Int
    init(_ d:[String:Any]) {
        state=d["state"] as? String ?? "running"; reason=d["reason"] as? String ?? ""
        lagSeconds=PreviewDrafts.number(d["lag_seconds"]) ?? 0; epoch=d["epoch"] as? Int ?? 1
    }
}

/// What the transcript tab holds about one meeting's drafts between polls. Keyed by meeting so a selection
/// change starts clean instead of painting one meeting's draft under another.
struct PreviewState:Equatable {
    var meeting=""; var cache:[String:PreviewDraft]=[:]; var session:PreviewSession?; var cursor:Double=0
}

enum PreviewDrafts {
    static let recordingBadge="Canlı taslak açık · ses buluta gidiyor"
    /// SQLite REAL columns arrive as NSNumber from the bridge, literals in tests as Int or Double.
    static func number(_ v:Any?)->Double? { (v as? Double) ?? (v as? Int).map(Double.init) ?? (v as? NSNumber)?.doubleValue }
    static let finalNotice="Taslak metin · toplantı bitince asıl yazıya çevirme bunun yerini alır; düzeltme ve isimlendirme o zaman açılır"

    /// Folds one `transcript_previews` reply into the cache. Polls may cross a reconnect, so the cache only
    /// moves forward: an answer with an older (epoch, revision) than the one kept is a stale response and is
    /// ignored, and a draft already final is never reopened. A reply for another meeting replaces nothing.
    static func merge(_ state:PreviewState,reply:[String:Any])->PreviewState {
        guard let meeting=reply["meeting"] as? String, !meeting.isEmpty else { return state }
        var next=state.meeting==meeting ? state : PreviewState(meeting:meeting)
        if let s=reply["status"] as? [String:Any] { next.session=PreviewSession(s) }
        for raw in reply["previews"] as? [[String:Any]] ?? [] {
            let d=PreviewDraft(raw); guard !d.id.isEmpty else { continue }
            next.cursor=max(next.cursor,d.updated)
            if let kept=next.cache[d.id] {
                if kept.status=="final" { continue }
                if (d.epoch,d.revision) <= (kept.epoch,kept.revision) { continue }
            }
            next.cache[d.id]=d
        }
        return next
    }

    /// The drafts worth a line, in audio order. A finished meeting shows none (its transcript is the answer),
    /// and a draft whose audio the final rows of the same source already cover gives way to them: the result
    /// replaces the draft where it exists, the draft fills in only where the result has not arrived yet.
    static func visible(_ state:PreviewState,finals:[Row],complete:Bool)->[PreviewDraft] {
        if complete { return [] }
        return state.cache.values.filter { $0.hasText && !covered($0,by:finals) }.sorted { ($0.start,$0.id) < ($1.start,$1.id) }
    }
    static func covered(_ d:PreviewDraft,by finals:[Row])->Bool {
        let same=finals.filter { $0.source.isEmpty || d.source.isEmpty || $0.source==d.source }
        guard d.end>d.start else { return same.contains { $0.start<=d.start && d.start<=$0.end } }
        let overlap=same.reduce(0.0) { $0+max(0,min($1.end,d.end)-max($1.start,d.start)) }
        return overlap >= (d.end-d.start)/2
    }
    /// Spans the worker gave up on (failed, skipped, unknown after a crash): said as a count, never as text.
    static func missingCount(_ state:PreviewState)->Int { state.cache.values.filter { ["failed","skipped","unknown"].contains($0.status) }.count }

    static func lagText(_ seconds:Double)->String {
        if seconds<3 { return "güncel" }
        if seconds<90 { return "≈\(Int(seconds.rounded())) sn geride" }
        return "≈\(Int((seconds/60).rounded())) dk geride"
    }
    static let pauseReasons=["cost":"maliyet sınırına ulaşıldı","audio_seconds":"gönderilecek ses süresi sınırına ulaşıldı","disk":"disk alanı azaldı",
        "backlog":"taslak kaydın çok gerisinde kaldı","age":"bekleyen ses parçaları eskidi","network":"OpenRouter’a ulaşılamıyor",
        "adapter_unavailable":"OpenRouter bağlantısı kurulamadı","internal":"beklenmeyen bir sorun oluştu","grace_exceeded":"son parçaların taslağı yetişmedi"]
    /// One sentence over the drafts. Every non-running state also says what still happens: the recording
    /// goes on and the real transcript is still made at the end, so a paused draft never reads as a lost meeting.
    static func statusLine(_ state:PreviewState,recording:Bool)->String {
        let missing=missingCount(state); let tail=missing>0 ? " · \(missing) parçanın taslağı alınamadı" : ""
        guard let s=state.session else { return recording ? "Canlı taslak bekleniyor · ilk ses parçası kapanınca gelir" : "Canlı taslak yok" }
        let reason=pauseReasons[s.reason] ?? (s.reason.isEmpty ? "" : "bir sınır aşıldı")
        switch s.state {
        case "paused": return "Canlı taslak duraklatıldı"+(reason.isEmpty ? "" : " · \(reason)")+" · kayıt sürüyor, asıl yazıya çevirme toplantı sonunda yapılır"+tail
        case "stopped": return "Canlı taslak durdu"+(reason.isEmpty ? "" : " · \(reason)")+" · asıl yazıya çevirme toplantı sonunda yapılır"+tail
        case "disabled": return "Canlı taslak kapalı"+tail
        default: return (recording ? "Canlı taslak · \(lagText(s.lagSeconds))" : "Canlı taslak · kayıt bitti, asıl yazıya çevirme bekleniyor")+tail
        }
    }
}
