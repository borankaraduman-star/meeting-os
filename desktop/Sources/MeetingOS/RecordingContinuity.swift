import Foundation

/// What capture_state says about a recording that had to survive something: the audio stream was rebuilt, the
/// whole capture helper was replaced, the Mac slept. The owner is in a meeting while this happens, so the only
/// thing the app is allowed to do is put one passive line in the recorder panel — never a notification, never a
/// sound, and never the same line twice for the same event.
public enum RecordingContinuity {
    /// live.py RELAUNCH_LIMIT: past this the supervisor has stopped trying and silence really is silence.
    public static let relaunchBudget = 5
    public static let staleSeconds: Double = 60

    public struct State: Equatable {
        public var capture = ""
        public var restarts = 0
        public var relaunches = 0
        public var wakes = 0
        public var gapSeconds: Double = 0
        public var lastEventAge: Double?
        public init() {}
        public init(capture: String = "", restarts: Int = 0, relaunches: Int = 0, wakes: Int = 0, gapSeconds: Double = 0, lastEventAge: Double? = nil) {
            self.capture = capture; self.restarts = restarts; self.relaunches = relaunches
            self.wakes = wakes; self.gapSeconds = gapSeconds; self.lastEventAge = lastEventAge
        }
    }

    public static func read(_ capture: [String: Any]) -> State {
        State(capture: capture["state"] as? String ?? "",
              restarts: count(capture["restarts"]), relaunches: count(capture["relaunches"]), wakes: count(capture["wakes"]),
              gapSeconds: seconds(capture["gap_seconds"]) + seconds(capture["wake_gap_seconds"]),
              lastEventAge: capture["last_event_age"].flatMap(number))
    }

    /// The recording is not coming back on its own: the helper reported a fatal error, or nothing has been
    /// written for a minute and the supervisor has already used up its relaunches.
    public static func interrupted(_ state: State) -> Bool {
        if state.capture == "error" { return true }
        return state.relaunches >= relaunchBudget && (state.lastEventAge ?? 0) > staleSeconds
    }

    public static func notice(from previous: State, to current: State) -> String? {
        if interrupted(current) { return interrupted(previous) ? nil : "Kayıt kesildi · yeniden başlatılıyor" }
        guard current.restarts > previous.restarts || current.relaunches > previous.relaunches || current.wakes > previous.wakes else { return nil }
        let gap = Int(current.gapSeconds.rounded())
        return gap > 0 ? "Kayıt devam ediyor · \(gap) sn boşluk" : "Kayıt devam ediyor"
    }

    private static func number(_ value: Any) -> Double? {
        guard let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
        let d = n.doubleValue
        return d.isFinite ? d : nil
    }
    private static func count(_ value: Any?) -> Int { Int(max(0, min(100000, value.flatMap(number) ?? 0))) }
    private static func seconds(_ value: Any?) -> Double { max(0, min(86400, value.flatMap(number) ?? 0)) }
}
