import Foundation

/// Disk usage from the `storage_report` bridge action. Sizes are bytes; nothing here deletes.
struct StorageReport {
    struct Entry:Identifiable { let meeting:String; let title:String; let bytes:Int; let active:Bool; var id:String { meeting } }
    let recordings:Int; let imports:Int; let database:Int; let teamCache:Int; let logs:Int; let meetings:[Entry]
    /// The text retention countdown, or nil when the setting is off or nothing is close. The one storage
    /// setting that deletes something no pass can rebuild, so the card says it before the pass runs.
    var textRetentionWarning:String?=nil
    /// Everything the app keeps in its data folder, not just the part made of meetings: a Mac whose team cache
    /// has quietly grown must not read as smaller than it is (Codex P2 #11).
    var total:Int { recordings+imports+database+teamCache+logs }
    /// Audio is recordings and imports together — one row, because the user thinks in “ses”, not in folders.
    var audio:Int { recordings+imports }
    static func parse(_ response:[String:Any])->StorageReport {
        let totals=response["totals"] as? [String:Any] ?? [:]
        let entries=(response["meetings"] as? [[String:Any]] ?? []).compactMap { d->Entry? in
            guard let id=d["meeting"] as? String, !id.isEmpty else { return nil }
            return Entry(meeting:id,title:d["title"] as? String ?? "",bytes:d["bytes"] as? Int ?? 0,active:d["active"] as? Bool ?? false)
        }
        return StorageReport(recordings:totals["recordings"] as? Int ?? 0,imports:totals["imports"] as? Int ?? 0,database:totals["database"] as? Int ?? 0,
                             teamCache:totals["team_cache_bytes"] as? Int ?? 0,logs:totals["logs_bytes"] as? Int ?? 0,meetings:entries,
                             textRetentionWarning:(response["text_retention_warning"] as? [String:Any])?["line"] as? String)
    }
    /// The N largest meetings that own audio; ties keep the backend order (newest first).
    func largest(_ count:Int)->[Entry] { Array(meetings.sorted { $0.bytes > $1.bytes }.prefix(count)) }
    /// Decimal units like Finder, Turkish decimal comma: 1,8 GB · 340 MB · 0,4 MB.
    static func format(bytes:Int)->String {
        let b=Double(max(0,bytes))
        if b >= 1_000_000_000 { return String(format:"%.1f GB",b/1_000_000_000).replacingOccurrences(of:".",with:",") }
        if b >= 10_000_000 { return "\(Int((b/1_000_000).rounded())) MB" }
        return String(format:"%.1f MB",b/1_000_000).replacingOccurrences(of:".",with:",")
    }
}
