import Foundation

/// A launch that never happened must not be announced. `Model.launch` no-ops while its process slot is taken:
/// the record helper keeps draining for up to ~30 s after ⌃⌥R stops it, and a running job blocks the next job.
/// The status line used to claim "Kayıt başladı" / "Özet hazırlanıyor…" either way.
enum LaunchOutcome {
    static let recordStarted="Kayıt başladı · ⌃⌥R ile bitir, ⌃⌥M ile an işaretle"
    static let recordBusy="Önceki kayıt kapanıyor · birkaç saniye sonra tekrar deneyin"
    /// nil leaves the status line untouched: a refused job launch has nothing new to say.
    static func activity(started:Bool,onStart:String,onRefusal:String?=nil)->String? { started ? onStart : onRefusal }
}
