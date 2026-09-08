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
}
