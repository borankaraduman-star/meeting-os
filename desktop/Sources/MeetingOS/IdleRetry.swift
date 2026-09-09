import Foundation

/// When OpenRouter was down, the meeting must not wait for the user to remember it. The queue asks the
/// Python side for one candidate while the Mac is genuinely idle and hands it to the existing finalize path.
/// Pure decisions only: no timer of its own, no bridge call, no process.
enum IdleRetry {
    static let interval:TimeInterval=600          // at most one question every ten idle minutes
    static let pressureGrace:TimeInterval=300     // a memory-pressure warning keeps the queue quiet this long
    static let hintInterval:TimeInterval=24*3600  // a blocked key/credit is worth one passive notice a day, no more

    /// Nothing of the user's may be running: no recording, no job, an empty finalize queue, no Zoom meeting
    /// (its window list also covers the screen-share toolbar) and no recent memory pressure.
    static func shouldAsk(enabled:Bool,recording:Bool,hasJob:Bool,queued:Bool,zoomOpen:Bool,pressureAt:Date?,last:Date?,now:Date=Date())->Bool {
        guard enabled,!recording,!hasJob,!queued,!zoomOpen else { return false }
        if let pressure=pressureAt, now.timeIntervalSince(pressure)<pressureGrace { return false }
        return last.map { now.timeIntervalSince($0) >= interval } ?? true
    }

    /// One quiet, permanent line for meetings stuck on something only the user can fix. Never a storm.
    static func blockedHint(_ blocked:[[String:Any]])->String? {
        guard !blocked.isEmpty else { return nil }
        let kinds=Set(blocked.compactMap { $0["kind"] as? String })
        let what=kinds==["credit"] ? "OpenRouter kredisi bitti" : (kinds==["auth"] ? "OpenRouter anahtarı geçersiz" : "OpenRouter anahtarı veya kredisi engelliyor")
        return "\(what) · \(blocked.count) toplantı bekliyor · Ayarlar → Sistem → OpenRouter anahtarı"
    }

    static func shouldNotifyBlocked(count:Int,last:Date?,now:Date=Date())->Bool {
        guard count>0 else { return false }
        return last.map { now.timeIntervalSince($0) >= hintInterval } ?? true
    }
}
