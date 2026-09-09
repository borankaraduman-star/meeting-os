import Foundation

/// Disk usage from the `storage_report` bridge action. Sizes are bytes; nothing here deletes.
struct StorageReport {
    struct Entry:Identifiable { let meeting:String; let title:String; let bytes:Int; let active:Bool; var id:String { meeting } }
    let recordings:Int; let imports:Int; let database:Int; let meetings:[Entry]
    var total:Int { recordings+imports+database }
    static func parse(_ response:[String:Any])->StorageReport {
        let totals=response["totals"] as? [String:Any] ?? [:]
        let entries=(response["meetings"] as? [[String:Any]] ?? []).compactMap { d->Entry? in
            guard let id=d["meeting"] as? String, !id.isEmpty else { return nil }
            return Entry(meeting:id,title:d["title"] as? String ?? "",bytes:d["bytes"] as? Int ?? 0,active:d["active"] as? Bool ?? false)
        }
        return StorageReport(recordings:totals["recordings"] as? Int ?? 0,imports:totals["imports"] as? Int ?? 0,database:totals["database"] as? Int ?? 0,meetings:entries)
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
