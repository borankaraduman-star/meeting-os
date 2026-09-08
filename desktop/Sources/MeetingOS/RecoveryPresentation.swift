import Foundation

enum RecoveryPresentation {
    static func canRetry(status:String,hasCapture:Bool,owner:String)->Bool {
        hasCapture && (["incomplete","provisional","failed"].contains(status) || (status=="processing" && owner=="interrupted"))
    }
    static func canCancel(jobKind:String?,running:Bool,requested:Bool)->Bool {
        running && jobKind == "retry" && !requested
    }
}
