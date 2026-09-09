import Foundation

// A capture-owned receipt is independent of selection and delayed library polling.
enum RecordingCompletion {
    static func retryMeeting(_ receipt:[String:Any],capture:String)->String? {
        guard let received=receipt["capture_dir"] as? String, received.hasPrefix("/"), capture.hasPrefix("/"),
              URL(fileURLWithPath:received).standardizedFileURL.resolvingSymlinksInPath().path == URL(fileURLWithPath:capture).standardizedFileURL.resolvingSymlinksInPath().path,
              receipt["status"] as? String == "provisional",
              let chunks=receipt["finalized_chunks"] as? Int, chunks>0,
              let mid=receipt["meeting"] as? String, !mid.isEmpty else { return nil }
        return mid
    }
    /// One calm line for a recording whose supervisor had something to complain about — a helper that had to be
    /// killed after stop, a relaunch budget that ran out. The audio is on disk and the final pass is already
    /// running, so this reassures; it is never an error banner over a meeting that was saved.
    static func notice(_ receipt:[String:Any])->String? {
        guard ((receipt["errors"] as? [String]) ?? []).contains(where:{ !$0.isEmpty }) else { return nil }
        return "Kayıt sırasında bir aksama oldu · alınan ses korundu, yazıya çevriliyor"
    }
}
