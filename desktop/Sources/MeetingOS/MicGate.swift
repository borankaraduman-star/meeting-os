import Foundation

/// Whose voice belongs to the meeting. Until now the microphone track was recorded *and* transcribed for the
/// whole recording, so a corridor conversation held while Zoom was muted arrived in the transcript as the
/// owner's own words (Boran, 11 Eyl 2026: "Mikrofondan gelen her sesi almak yerine sadece toplantıda unmute
/// edince … alsın"). The gate decides, second by second, whether the microphone is part of the meeting; every
/// change is journalled into the capture folder and finalize skips the mic pieces that fall outside.
///
/// Pure rule, no I/O: the caller hands in the mode, what Zoom says and whether the user forced the mic open.
enum MicGate {
    static let key="micMode"
    static let modes=["zoom","manual","always"]
    /// One JSON line per state change, in the capture folder, written exactly the way `markMoment` writes
    /// `markers.jsonl`. It is deliberately NOT `capture-native.jsonl`: that file belongs to the capture helper,
    /// its first line has to be the helper's own `started` (the marker drift curve is measured from it), and
    /// `events.jsonl` may not exist before the recorder process creates it. `meeting_os/audio.py` reads this
    /// file, and falls back to gate lines found inside either journal.
    static let journal="mic-gate.jsonl"
    static func normalize(_ mode:String?)->String { let m=mode ?? ""; return modes.contains(m) ? m : "zoom" }
    /// The stored preference. Default `zoom`: follow the Zoom mute state, and record nothing when it is unknown.
    static var mode:String { normalize(UserDefaults.standard.string(forKey:key)) }
    static func label(_ mode:String)->String { ["zoom":"Zoom’u izle","manual":"Elle","always":"Her zaman"][normalize(mode)] ?? "Zoom’u izle" }

    /// `zoomMuted` is nil whenever the answer is unknown: no Zoom meeting, no Accessibility grant, a menu that
    /// could not be read. Unknown counts as muted — a gate that guesses "open" is the bug this exists to fix.
    /// The per-recording override wins over every mode: "Sesimi de kaydet" means now, whatever Zoom thinks.
    static func state(mode:String,zoomOpen:Bool,zoomMuted:Bool?,manualOn:Bool)->(on:Bool,reason:String) {
        if manualOn { return (true,"manual") }
        switch normalize(mode) {
        case "always": return (true,"always")
        case "manual": return (false,"manual")
        default: return (zoomOpen && zoomMuted==false,"zoom")
        }
    }

    /// The half-sentence after "açık"/"kapalı": why the microphone is where it is, in the menu bar menu.
    static func detail(mode:String,zoomOpen:Bool,zoomMuted:Bool?,manualOn:Bool,trusted:Bool=true)->String {
        if manualOn { return "elle" }
        switch normalize(mode) {
        case "always": return "her zaman"
        case "manual": return "elle açılmadı"
        default:
            if zoomMuted==true { return "Zoom sessizde" }
            if zoomMuted==false { return "Zoom’da ses açık" }
            if !trusted { return "Erişilebilirlik izni yok" }
            return zoomOpen ? "Zoom durumu okunamadı" : "Zoom toplantısı yok"
        }
    }
    static func statusLine(mode:String,zoomOpen:Bool,zoomMuted:Bool?,manualOn:Bool,trusted:Bool=true)->String {
        let on=state(mode:mode,zoomOpen:zoomOpen,zoomMuted:zoomMuted,manualOn:manualOn).on
        return "Mikrofon: "+(on ? "açık" : "kapalı")+" · "+detail(mode:mode,zoomOpen:zoomOpen,zoomMuted:zoomMuted,manualOn:manualOn,trusted:trusted)
    }
    /// Menu bar / panel label of the per-recording override.
    static func overrideLabel(_ on:Bool)->String { (on ? "Sesimi kaydetme" : "Sesimi de kaydet")+"  ⌃⌥V" }

    /// One journal line. `seconds` counts from the app's record start, the same origin `Markers.line` uses, and
    /// `wall` is the absolute moment — finalize puts both on the capture helper's timeline before comparing.
    static func line(on:Bool,reason:String,seconds:Double,now:Date=Date())->String {
        let payload:[String:Any]=["kind":"mic_gate","state":on ? "on" : "off","t":(max(0,seconds)*10).rounded()/10,"reason":reason,
                                  "created":ISO8601DateFormatter().string(from:now),"wall":(now.timeIntervalSince1970*1000).rounded()/1000]
        return (try? String(data:JSONSerialization.data(withJSONObject:payload),encoding:.utf8)) ?? "{}"
    }
}
