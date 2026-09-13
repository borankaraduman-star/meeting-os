import Foundation

/// Stopping a recording, as a state machine. `stop()` used to send one SIGINT and flip `recording` false on
/// the same line: a supervisor that was wedged (a stuck ffmpeg, a network volume) never exited, every stop
/// control went disabled because the app already believed the recording was over, and a second press was a
/// no-op. Force Quit was the only way out. Now the signal escalates and the UI keeps the recording until the
/// child is actually gone — or until we have killed it.
enum StopEscalation {
    enum Signal:Equatable { case interrupt, terminate, kill }
    static let termAfter:TimeInterval=5, killAfter:TimeInterval=10
    /// What still has to be sent, `elapsed` seconds after the first press. nil = nothing new; wait.
    static func next(elapsed:TimeInterval,alive:Bool,sent:Signal?)->Signal? {
        guard alive else { return nil }        // it exited on its own: never signal a dead pid
        if sent==nil { return .interrupt }     // SIGINT first — it is the one the supervisor handles cleanly
        if elapsed >= killAfter, sent != .kill { return .kill }
        if elapsed >= termAfter, sent == .interrupt { return .terminate }
        return nil
    }
    /// May the UI say the recording is over? Only when the child is gone, or when SIGKILL has been sent and
    /// there is nothing further to escalate to.
    static func finished(alive:Bool,sent:Signal?)->Bool { !alive || sent == .kill }
    /// A second press is the user telling us the helper is wedged. It does not restart the clock (that would
    /// make every press postpone the kill); it brings the next step forward to now.
    static func bringForward(sent:Signal?)->TimeInterval {
        switch sent {
        case .none: return 0
        case .interrupt: return termAfter
        case .terminate: return killAfter
        case .kill: return killAfter        // nothing left above SIGKILL
        }
    }
    static let notResponding="Kayıt yardımcısı yanıt vermiyor · kapatılıyor"
    static let killed="Kayıt yardımcısı durduruldu · biten ses parçaları korunuyor"
}

/// ⌘Q. `.terminateLater` had no deadline: the only `reply(toApplicationShouldTerminate:true)` sat inside a
/// child's termination handler, behind another bridge round-trip, so a job that never answered left the app
/// in a state no keystroke could finish. The deadline is the app's promise that quit always completes.
enum QuitSequence {
    static let deadlineSeconds:TimeInterval=8
    /// Debounce for the name field. The name used to be written at quit, synchronously, from the main thread
    /// (a Python interpreter, up to ten seconds); saving it a moment after typing stops means quit has
    /// nothing left to do.
    static let nameDebounceSeconds:TimeInterval=1
    /// A recording that is still draining gets the whole escalation ladder before the app gives up on it:
    /// replying "yes, quit" at eight seconds would leave a wedged helper running with nobody left to kill it.
    static func deadline(draining:Bool)->TimeInterval { draining ? StopEscalation.killAfter+3 : deadlineSeconds }
}
