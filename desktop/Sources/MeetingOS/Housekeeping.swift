import Foundation

/// When the hourly housekeeping sweep may run, and what it is allowed to say afterwards.
///
/// The sweep is the heaviest pass in the product (FLAC re-encode of the whole library, team sync, retention,
/// two calibration replays, the experiments). Its "last run" used to be a plain in-memory var, nil at every
/// launch, so the pass was due on the first poll of every run: three restarts a day, three sweeps, one of them
/// while the user was recording their first meeting. The stamp lives in `UserDefaults` now, and the schedule
/// is pure arithmetic so it can be tested without a clock.
enum HousekeepingSchedule {
    static let interval:TimeInterval=3600
    static let lastRunKey="lastHousekeepingAt"
    static let streaksKey="housekeepingFailureStreaks"
    static func isDue(last:Date?,now:Date=Date(),interval:TimeInterval=interval)->Bool {
        guard let last else { return true }
        let elapsed=now.timeIntervalSince(last)
        // A clock that jumped backwards (timezone change, NTP correction) must not lock the sweep out for
        // hours: a stamp in the future is a broken stamp, not a recent run.
        return elapsed >= interval || elapsed < 0
    }

    /// Turkish name of a sweep step, for the one line the Settings card shows. An unknown key (a newer Python
    /// side) is printed as it came rather than dropped: a nameless failure is still a failure.
    static func label(_ step:String)->String {
        switch step {
        case "team","team_sync": return "ekip eşitleme"
        case "archive","audio_archive": return "ses arşivleme"
        case "retention","cleanup": return "eski ses silme"
        case "text_retention": return "metin saklama"
        case "calibration": return "kalibrasyon"
        case "team_effect": return "ekip ölçümü"
        case "experiments": return "deneyler"
        case "preferences": return "özet tercihleri"
        case "task_errors": return "görev hataları"
        case "learning": return "öğrenme kaydı"
        default: return step
        }
    }
    /// Consecutive failures per step. A step missing from this pass's `failures` worked, so its count goes
    /// away — "3 kez üst üste" has to mean three passes in a row, not three times since the app was installed.
    static func streaks(previous:[String:Int],failures:[String:String])->[String:Int] {
        var next:[String:Int]=[:]
        for step in failures.keys { next[step]=(previous[step] ?? 0)+1 }
        return next
    }
    /// The one short line for Ayarlar → Depolama. nil = the sweep did everything it was asked to, say nothing:
    /// a permanent green "bakım tamam" is noise, while a failure that repeats in silence is finding #3.
    static func note(failures:[String:String],skipped:[String],streaks:[String:Int])->String? {
        if !failures.isEmpty {
            // Worst first, by how long it has been failing; the key breaks ties so the line does not flicker
            // between two equally old failures from one hour to the next.
            let worst=failures.keys.sorted { a,b in
                let sa=streaks[a] ?? 1, sb=streaks[b] ?? 1
                return sa==sb ? a<b : sa>sb
            }[0]
            let count=streaks[worst] ?? 1
            var line="Bakım: \(label(worst)) "+(count>1 ? "\(count) kez üst üste başarısız oldu" : "başarısız oldu")
            if failures.count>1 { line+=" · \(failures.count-1) adım daha" }
            return line
        }
        guard let first=skipped.sorted().first else { return nil }
        return "Bakım: \(label(first)) atlandı"+(skipped.count>1 ? " · \(skipped.count-1) adım daha" : "")
    }
    /// What the app keeps out of a `storage_housekeeping` answer. Both keys are optional on purpose: the Python
    /// side gains them separately, and an older bridge that reports neither must read as "nothing failed".
    static func outcome(_ answer:[String:Any])->(failures:[String:String],skipped:[String]) {
        let failures=answer["failures"] as? [String:String] ?? [:]
        let skipped=(answer["skipped"] as? [String]) ?? ((answer["skipped"] as? [String:Any]).map { Array($0.keys) } ?? [])
        return (failures,skipped)
    }
}
