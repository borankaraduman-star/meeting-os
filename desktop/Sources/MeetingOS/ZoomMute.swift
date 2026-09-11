import AppKit
import ApplicationServices
import Foundation

/// Is the local user's microphone open in the Zoom meeting? Zoom publishes no API for it, but its own menu
/// says so: the **Meeting** menu carries "Mute Audio" while the mic is live and "Unmute Audio" while it is
/// muted (Turkish: "Sesi Kapat" / "Sesi Aç"). The menu is read through the Accessibility API, which needs the
/// app to be AX-trusted; without that grant every reading is `nil` and `MicGate` treats nil as muted, so an
/// ungranted Mac records the owner's voice only while the ⌃⌥V override is on.
///
/// Everything here fails soft and nothing runs on the main thread: a hung Zoom must never freeze the app.
enum ZoomMute {
    /// Menu bar titles of Zoom's meeting menu, lowercased.
    static let menuTitles=["meeting","toplantı"]
    /// Bound on every AX round trip. A Zoom that does not answer is unknown, not a stall.
    static let timeout:Float=0.4

    /// Menu item titles → is the microphone muted? Pure, so every Zoom localisation is a test rather than a
    /// live meeting. "Unmute" is asked first: it contains "mute".
    static func verdict(titles:[String])->Bool? {
        let clean=titles.map { $0.lowercased().trimmingCharacters(in:.whitespacesAndNewlines) }
        if clean.contains(where:{ $0.contains("unmute audio") || $0.contains("sesi aç") }) { return true }
        if clean.contains(where:{ $0.contains("mute audio") || $0.contains("sesi kapat") }) { return false }
        return nil
    }

    static func trusted()->Bool { AXIsProcessTrusted() }
    /// The one call that makes macOS offer the Accessibility pane. Returns the grant as it stands right now —
    /// the answer only ever changes after the user acts in System Settings, so the caller re-reads later.
    @discardableResult static func requestTrust()->Bool {
        AXIsProcessTrustedWithOptions([kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String:true] as CFDictionary)
    }

    private static func attribute(_ element:AXUIElement,_ name:String)->CFTypeRef? {
        var value:CFTypeRef?
        guard AXUIElementCopyAttributeValue(element,name as CFString,&value)==AXError.success else { return nil }
        return value
    }
    private static func element(_ value:CFTypeRef?)->AXUIElement? {
        guard let value, CFGetTypeID(value)==AXUIElementGetTypeID() else { return nil }
        return (value as! AXUIElement)
    }
    private static func children(_ element:AXUIElement)->[AXUIElement] { (attribute(element,kAXChildrenAttribute as String) as? [AXUIElement]) ?? [] }
    private static func title(_ element:AXUIElement)->String { (attribute(element,kAXTitleAttribute as String) as? String) ?? "" }

    /// zoom.us → menu bar → "Meeting"/"Toplantı" → the titles of its items. Blocking AX calls, so this is only
    /// ever called from `stateAsync`'s background queue. Every failure — Zoom not running, no grant, no such
    /// menu, no meeting — is nil.
    static func read()->Bool? {
        guard AXIsProcessTrusted() else { return nil }
        guard let zoom=NSRunningApplication.runningApplications(withBundleIdentifier:ZoomWatch.bundle).first else { return nil }
        let app=AXUIElementCreateApplication(zoom.processIdentifier)
        AXUIElementSetMessagingTimeout(app,timeout)
        guard let bar=element(attribute(app,kAXMenuBarAttribute as String)) else { return nil }
        for item in children(bar) {
            guard menuTitles.contains(title(item).lowercased()) else { continue }
            // A menu bar item owns one child, the menu itself; its children are the entries we read.
            let entries=children(item).flatMap { children($0) }
            if let muted=verdict(titles:entries.map(title)) { return muted }
        }
        return nil
    }

    /// The reading the poll uses: the AX walk hops to a utility queue and comes back as one optional Bool.
    @MainActor static func stateAsync() async -> Bool? {
        await withCheckedContinuation { cont in DispatchQueue.global(qos:.utility).async { cont.resume(returning:read()) } }
    }
}
