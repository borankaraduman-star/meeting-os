import Foundation

enum RecoveryPresentation {
    static func canRetry(status:String,hasCapture:Bool,owner:String)->Bool {
        hasCapture && owner != "active" && (status != "provisional" || owner == "interrupted") && (["incomplete","provisional","failed"].contains(status) || (status=="processing" && owner=="interrupted"))
    }
    static func recordingLabel(recording:Bool,jobKind:String?)->String {
        recording ? "Kaydı bitir" : (jobKind == "record" ? "Kayıt durduruluyor…" : "Yeni kayıt")
    }
    static func canCancel(jobKind:String?,running:Bool,requested:Bool)->Bool {
        running && ["retry","openrouter-import"].contains(jobKind ?? "") && !requested
    }
}
