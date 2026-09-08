import Foundation

/// Logs keep the full diagnostic; the main-thread UI only receives bounded text.
enum ErrorPresentation {
    static func summary(_ text:String)->String {
        let prefix=String(text.prefix(401))
        if prefix.count<=400 { return prefix }
        return String(prefix.prefix(300))+"… Ayrıntılar: last-job.log / tanılama raporu."
    }
    static func logSummary(_ url:URL)->String {
        guard let file=try? FileHandle(forReadingFrom:url) else { return "İşlem tamamlanamadı" }
        defer { try? file.close() }
        do {
            let size=try file.seekToEnd()
            try file.seek(toOffset:size>8192 ? size-8192 : 0)
            let tail=String(decoding:try file.read(upToCount:8192) ?? Data(),as:UTF8.self)
            return summary(tail.split(separator:"\n").last.map(String.init) ?? "İşlem tamamlanamadı")
        } catch { return "İşlem tamamlanamadı · Tanılama kaydını kontrol edin" }
    }
}
