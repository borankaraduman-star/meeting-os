import Foundation

/// After a relaunch, the most recent meeting whose processing was interrupted is selected so its
/// preserved audio and recovery actions are the first thing on screen. Pure; runs once per launch.
enum RelaunchRestore {
    static let restorableStates:Set<String>=["incomplete","provisional","processing"]
    static func pick(meetings:[Meeting])->Meeting? {
        meetings
            .filter { restorableStates.contains($0.status) && $0.recoveryState != "active" }
            .max { $0.created < $1.created }   // ISO-8601 UTC timestamps sort lexically
    }
    static func headline(_ meeting:Meeting)->String {
        "Sesiniz korundu · işlem şurada kaldı: \(statusLabel(meeting.displayStatus))"
    }
}
