import SwiftUI
import AppKit

/// Göze batma: while the user is on a call — and above all while they are sharing their screen — nothing about
/// Meeting OS should be readable by the other people in the meeting. Three decisions, all pure so they can be
/// tested without a window server:
///   • the menu bar label while recording (a recording must look exactly like not recording),
///   • whether the floating recorder panel may be on screen,
///   • what `sharingType` the app's own windows carry.
/// The reassurance that a recording is still running does not disappear: it moves into the menu the user opens
/// themselves (QuickMenu still says "Kayıt sürüyor · 12:34"), which is the one place nobody else is looking.
enum DiscreetMode {
    static let key="discreetMode"
    /// Default ON: the safe reading is the discreet one, and the user has to opt into being visible.
    static var enabled:Bool { UserDefaults.standard.object(forKey:key) as? Bool ?? true }

    /// What the menu bar item draws. `text` nil means the glyph alone — no title, no elapsed time.
    struct MenuBarLook:Equatable { let glyph:String; let text:String? }

    /// The idle glyph, which depends only on whether a Zoom meeting is open. Discreet mode reuses it verbatim
    /// while recording, so starting or ending a recording changes nothing at all in the menu bar: no red dot,
    /// no clock, no "kaydediyor", nothing that moves. Somebody watching the shared screen cannot tell the
    /// difference between a recorded meeting and a quiet one.
    static func idleGlyph(zoomOpen:Bool)->String { zoomOpen ? "video.badge.waveform" : "waveform" }

    static func menuBar(recording:Bool,discreet:Bool,zoomOpen:Bool,elapsed:String)->MenuBarLook {
        let idle=MenuBarLook(glyph:idleGlyph(zoomOpen:zoomOpen),text:nil)
        guard recording else { return idle }                      // not recording: unchanged, in both modes
        guard discreet else { return MenuBarLook(glyph:"record.circle.fill",text:elapsed) }   // discreet off: today's label
        return idle
    }

    /// The floating panel may only be on screen while a recording is running and the user has asked for it —
    /// and never while they are sharing their screen with discreet mode on. `sharingType = .none` already keeps
    /// it out of the capture stream, but a panel that is merely invisible to Zoom is still a panel the presenter
    /// has to trust; hiding it outright also keeps it out of a phone camera pointed at the screen and out of any
    /// capture path that does not honour the flag.
    /// Boran, 11 Sep 2026 (photo of the panel floating over a live Zoom call, seen by the room): "Kaldır bunu
    /// direkt." The panel is gone for good: whatever the inputs, it never comes back. Stop, markers and the
    /// elapsed time live in the menu bar menu and the shortcuts (⌃⌥R, ⌃⌥M). The signature stays so nothing
    /// that reads it has to change.
    static func panelVisible(recording:Bool,panelEnabled:Bool,discreet:Bool,sharing:Bool)->Bool { false }

    /// Main-window privacy. With `.none` the app's windows are excluded from screen capture entirely, so a
    /// shared full screen never shows the transcript — which is exactly what is wanted. `.readOnly` is the
    /// system default and is what discreet mode restores when it is switched off.
    /// `.none` also blocks the user's OWN screenshots (⌘⇧4 draws the window black), so it is applied only while
    /// there is somebody to hide from: a real Zoom meeting or an active screen share. Boran, 11 Sep 2026: "özet ve
    /// kararları screenshot alamıyorum" — outside a meeting the windows are ordinary again.
    static func windowSharingType(discreet:Bool,inMeeting:Bool=true,sharing:Bool=true)->NSWindow.SharingType { discreet && (inMeeting || sharing) ? .none : .readOnly }

    /// A banner is the loudest thing the app can do on a shared screen, so nothing is delivered while a meeting
    /// is on screen, a recording is running, or the user is sharing. (Deliveries queue and land afterwards.)
    static func mayNotify(recording:Bool,meetingOpen:Bool,sharing:Bool)->Bool { !recording && !meetingOpen && !sharing }
}
