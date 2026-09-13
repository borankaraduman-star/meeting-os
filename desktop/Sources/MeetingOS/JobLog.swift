import Foundation

/// One log file per child, instead of the single `last-job.log` every process used to truncate under each
/// other. A recording and a finalize are deliberately allowed to run at the same time, so two children wrote
/// into one inode at independent offsets — and `ErrorPresentation.logSummary` then reported the *recorder's*
/// last line as the failed job's error. The name carries the job's own id; path building and pruning are pure
/// so both can be tested without a data folder.
enum JobLog {
    static let prefix="last-job-", suffix=".log"
    /// How many logs survive a launch. Enough to look back at the last few failures, small enough that the
    /// "Günlükler" figure in Ayarlar → Depolama never becomes a number anybody has to think about.
    static let keep=5
    /// A job id reaches us as a UUID, but a stray "/" or ":" would silently write outside the data folder.
    static func sanitize(_ jobId:String)->String {
        let safe=jobId.unicodeScalars.map { CharacterSet.alphanumerics.contains($0) || $0=="-" || $0=="_" ? Character($0) : "-" }
        return String(safe).isEmpty ? "job" : String(safe.prefix(64))
    }
    static func name(jobId:String)->String { prefix+sanitize(jobId)+suffix }
    static func url(dataDir:URL,jobId:String)->URL { dataDir.appendingPathComponent(name(jobId:jobId)) }
    static func isJobLog(_ name:String)->Bool { name.hasPrefix(prefix) && name.hasSuffix(suffix) }
    /// Which files to delete, newest `keep` kept. The caller hands over what the folder holds; this decides.
    static func stale(_ files:[(name:String,modified:Date)],keep:Int=keep)->[String] {
        let logs=files.filter { isJobLog($0.name) }.sorted { $0.modified==$1.modified ? $0.name>$1.name : $0.modified>$1.modified }
        return logs.count<=keep ? [] : logs[keep...].map(\.name)
    }
    /// The Python side reads `<data>/last-job.log` in several places (the heartbeat's error tail, the capture
    /// preview, `tighten_modes`). A symlink to the newest per-job log keeps all of that working — and
    /// `logs_bytes` already skips symlinks, so the disk total does not count the same file twice.
    static let compatName="last-job.log"
    static func linkLatest(dataDir:URL,to log:URL) {
        let link=dataDir.appendingPathComponent(compatName)
        let fm=FileManager.default
        try? fm.removeItem(at:link)   // a plain file left by an older version goes too; its job is over
        try? fm.createSymbolicLink(at:link,withDestinationURL:log)
    }
    /// The filesystem half: list, decide, delete. Failures are ignored on purpose — a log that cannot be
    /// removed must never stop the job the user just asked for.
    static func prune(dataDir:URL,keep:Int=keep) {
        let fm=FileManager.default
        guard let names=try? fm.contentsOfDirectory(atPath:dataDir.path) else { return }
        let files:[(name:String,modified:Date)]=names.filter(isJobLog).map { name in
            let date=(try? fm.attributesOfItem(atPath:dataDir.appendingPathComponent(name).path)[.modificationDate] as? Date) ?? nil
            return (name,date ?? Date.distantPast)
        }
        for name in stale(files,keep:keep) { try? fm.removeItem(at:dataDir.appendingPathComponent(name)) }
    }
}
