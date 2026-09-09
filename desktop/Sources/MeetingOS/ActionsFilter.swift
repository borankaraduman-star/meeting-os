import Foundation

/// The Görevlerim filter is a preference, not a per-meeting guess: it survives a meeting change and a
/// relaunch. When "Bana ait" is empty the view no longer switches the filter behind the user's back — it
/// says why the list is empty in one sentence and offers the switch as a button.
enum ActionsFilter {
    static let key="actionsFilter"
    static let all=["mine","meeting","all"]
    static func normalize(_ raw:String)->String { all.contains(raw) ? raw : "mine" }
    /// The one sentence under "Görev bulunamadı".
    static func emptyMessage(filter:String,meetingOpen:Int)->String {
        if filter=="mine" && meetingOpen>0 { return "Bu toplantıda \(meetingOpen) açık görev var ama hiçbiri sana atanmamış." }
        return "İsimsiz görevler Tüm görevler altında görünür; sahibini kaynakla doğrulayarak düzeltebilirsin."
    }
    /// The "Bu toplantı" shortcut only appears when it would actually show something.
    static func offersMeetingSwitch(filter:String,meetingOpen:Int)->Bool { filter=="mine" && meetingOpen>0 }
}
