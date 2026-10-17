import AppKit
import ApplicationServices
import AVFoundation
import CoreGraphics
import Foundation

/// The native side of the permission contract (docs/IZIN_ONBOARDING.md): the one place that talks to TCC, and its
/// scriptable twin. Everything that is not a system call — which URL to try on which macOS, what the chain of
/// fallbacks is, when a screen grant is called "needs relaunch" — lives in pure helpers so the tests never touch
/// AVCaptureDevice, CoreGraphics or Accessibility: those six calls are `PermissionSystemCalls`, injected.

// MARK: - Settings URLs

extension PermissionSettingsLink {
    /// The `PrivacySecurity.extension` form: the Settings app of macOS 13+ (Granola's accessibility and screen-recording
    /// guide use it, evidence 03b B2/B5).
    static let modernPrefix="x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?"

    /// Every URL worth trying for a pane, best first. macOS 13+: the new identifier, then the legacy one (it still
    /// resolves through the compatibility layer, and is what `SetupStatus.openPane` has always used); macOS 12-: only
    /// the legacy one. Nil when the grant does not exist on this OS.
    static func candidates(_ kind:PermissionKind,os:OperatingSystemVersion)->[URL] {
        guard PermissionFlow.supported(kind,os:os) else { return [] }
        let prefixes = os.majorVersion>=13 ? [modernPrefix,legacyPrefix] : [legacyPrefix]
        return prefixes.compactMap { URL(string:$0+kind.paneAnchor) }
    }
}

/// Opens a pane, then the general Privacy pane; false only when nothing opened. Shared by the live and the fake
/// provider so the fallback order is one tested piece of code.
struct PermissionSettingsOpener {
    var open:(URL)->Bool

    func openPane(_ kind:PermissionKind,os:OperatingSystemVersion)->Bool {
        for url in PermissionSettingsLink.candidates(kind,os:os) where open(url) { return true }
        if let general=PermissionSettingsLink.fallbackURL(os:os), open(general) { return true }
        return false
    }
}

// MARK: - Screen grant memory

/// Evidence for `needsRelaunch`. CGPreflightScreenCaptureAccess can keep answering false after the user switched the
/// grant on, until the process is reopened — but a bare `false` is also what a user who said no looks like, and
/// coming back from Settings proves nothing about what the user did there. So the verdict needs independent proof
/// that the grant exists (`grantEvidence`, e.g. the capture helper reporting screen_audio granted); the visit story
/// (asked, Settings opened, came back) is necessary but never sufficient. Without proof the answer is `denied`, and
/// the flow still offers a relaunch as an option (`relaunchSuggested`) with a truthful badge.
struct ScreenGrantMemory: Equatable {
    var requested=false
    var settingsOpened=false
    var returned=false

    mutating func noteRequest() { requested=true }
    mutating func noteSettingsOpened() { settingsOpened=true; returned=false }
    mutating func noteBecameActive() { if settingsOpened { returned=true } }

    func resolve(preflight:Bool,grantEvidence:Bool=false)->PermissionStatus {
        if preflight { return .authorized }
        return grantEvidence && requested && settingsOpened && returned ? .needsRelaunch : .denied
    }
}

// MARK: - Prompt ledger

/// Has THIS app ever put the macOS prompt for a grant on screen? Screen recording and Accessibility expose no
/// "not determined" — their preflight is a bare Bool, so a Mac that was never asked reads exactly like one that said
/// no. Calling that `denied` sent every first-time user straight to System Settings, where Meeting OS is not even
/// listed yet: only the prompt call (`CGRequestScreenCaptureAccess`, `AXIsProcessTrustedWithOptions(prompt)`) puts the
/// app into the list. So the app remembers its own asking (UserDefaults, injected): never asked → `notDetermined`
/// → the card offers "İzin iste" and the click runs the real prompt; asked and still off → `denied` → Settings.
/// Granola keeps the same kind of local "asked" memory for its Enable buttons (docs/IZIN_ONBOARDING.md, row 24).
struct PermissionPromptLedger {
    let defaults:UserDefaults
    static func key(_ kind:PermissionKind)->String { "permissionPromptAsked."+kind.rawValue }
    func asked(_ kind:PermissionKind)->Bool { defaults.bool(forKey:Self.key(kind)) }
    func noteAsked(_ kind:PermissionKind) { defaults.set(true,forKey:Self.key(kind)) }

    /// A prompt-only grant (no tri-state API): on is on; off is a question still to ask until the app has asked it.
    static func status(granted:Bool,asked:Bool)->PermissionStatus { granted ? .authorized : (asked ? .denied : .notDetermined) }
}

// MARK: - System calls

/// The six TCC calls the live provider makes, as values: `.live` is the real thing, tests hand in closures that
/// record and script. Nothing else in the provider touches the system, so its whole decision path is testable
/// without a prompt ever appearing.
struct PermissionSystemCalls {
    var microphoneStatus:()->AVAuthorizationStatus
    var requestMicrophone:(@escaping (Bool)->Void)->Void
    var screenPreflight:()->Bool
    var screenRequest:()->Bool
    var accessibilityTrusted:()->Bool
    var accessibilityRequest:()->Bool

    static let live=PermissionSystemCalls(
        microphoneStatus:{ AVCaptureDevice.authorizationStatus(for:.audio) },
        requestMicrophone:{ done in AVCaptureDevice.requestAccess(for:.audio,completionHandler:done) },
        screenPreflight:{ CGPreflightScreenCaptureAccess() },
        screenRequest:{ CGRequestScreenCaptureAccess() },     // shows macOS’s own prompt once; later calls only answer
        accessibilityTrusted:{ ZoomMute.trusted() },
        accessibilityRequest:{ ZoomMute.requestTrust() })     // the prompt, and what lists Meeting OS in the pane
}

// MARK: - Live provider

/// The real thing. `status` never prompts; `request` is only called from a click (the flow guarantees it).
/// The OS version, the URL opener, the defaults holding the prompt ledger and the system calls are injected, so
/// every branch of this class runs in tests; only `PermissionSystemCalls.live` itself is out of their reach.
final class LivePermissionProvider: PermissionProviding {
    /// One provider for the whole app: the screen-grant memory (requested → Settings opened → came back) is only
    /// meaningful if the flow, the setup list and the Settings rows all ask the same instance.
    static let shared=LivePermissionProvider()
    let osVersion:OperatingSystemVersion
    private let opener:PermissionSettingsOpener
    private let system:PermissionSystemCalls
    private let ledger:PermissionPromptLedger
    private var memory=ScreenGrantMemory()
    private var observer:NSObjectProtocol?
    private let center:NotificationCenter

    init(osVersion:OperatingSystemVersion=ProcessInfo.processInfo.operatingSystemVersion,
         center:NotificationCenter = .default,
         defaults:UserDefaults = .standard,
         system:PermissionSystemCalls = .live,
         open:@escaping (URL)->Bool={ NSWorkspace.shared.open($0) }) {
        self.osVersion=osVersion; self.center=center; self.system=system
        ledger=PermissionPromptLedger(defaults:defaults); opener=PermissionSettingsOpener(open:open)
        observer=center.addObserver(forName:NSApplication.didBecomeActiveNotification,object:nil,queue:.main) { [weak self] _ in
            self?.memory.noteBecameActive()
        }
    }
    deinit { if let observer { center.removeObserver(observer) } }

    // MARK: Pure mappings (tested)

    static func microphoneStatus(_ raw:AVAuthorizationStatus)->PermissionStatus {
        switch raw {
        case .authorized: return .authorized
        case .denied: return .denied
        case .notDetermined: return .notDetermined
        case .restricted: return .restricted
        @unknown default: return .unknown
        }
    }

    // MARK: PermissionProviding

    func status(_ kind:PermissionKind)->PermissionStatus {
        guard PermissionFlow.supported(kind,os:osVersion) else { return .unsupported }
        switch kind {
        case .microphone: return Self.microphoneStatus(system.microphoneStatus())
        case .systemAudio:
            let granted=system.screenPreflight()
            if !granted && !ledger.asked(.systemAudio) { return .notDetermined }
            return memory.resolve(preflight:granted)
        case .accessibility: return PermissionPromptLedger.status(granted:system.accessibilityTrusted(),asked:ledger.asked(.accessibility))
        }
    }

    func request(_ kind:PermissionKind,completion:@escaping (PermissionStatus)->Void) {
        let finish={ [weak self] in
            DispatchQueue.main.async { completion(self?.status(kind) ?? .unknown) }
        }
        switch kind {
        case .microphone:
            // Only a question macOS has not asked yet can be asked; anything else is a Settings matter and the
            // flow offers "Sistem Ayarları’nı aç" on the card instead.
            if system.microphoneStatus() == .notDetermined {
                system.requestMicrophone { _ in finish() }
            } else { finish() }
        case .systemAudio:
            // Noted before the call: whatever the prompt's fate, the next read is a real `denied`, never another ask.
            ledger.noteAsked(.systemAudio); memory.noteRequest()
            _=system.screenRequest()
            finish()
        case .accessibility:
            ledger.noteAsked(.accessibility)
            _=system.accessibilityRequest()
            // The pane is opened by the flow (requestFinished → .openSettings), not here: only the flow can turn a
            // failed open into the `settingsOpenFailed` recovery instead of leaving the user waiting on nothing.
            finish()
        }
    }

    @discardableResult func openSettings(_ kind:PermissionKind)->Bool {
        let opened=opener.openPane(kind,os:osVersion)
        if opened { memory.noteSettingsOpened() }
        return opened
    }

    func settingsURL(_ kind:PermissionKind)->URL? { PermissionSettingsLink.candidates(kind,os:osVersion).first }
}

// MARK: - Fake provider

/// A provider the tests (and the fixture render) script: statuses by kind, what `request` answers, whether URLs
/// open — and a record of every call. It touches nothing real.
final class FakePermissionProvider: PermissionProviding {
    let osVersion:OperatingSystemVersion
    var statuses:[PermissionKind:PermissionStatus]
    /// What a `request` leaves behind. Absent kind = the status stays as it was (a prompt that changed nothing).
    var requestOutcome:[PermissionKind:PermissionStatus]=[:]
    /// URLs that open; the rest fail. nil = every URL opens.
    var openableURLs:Set<URL>?
    /// Run on each status read, with the read count — lets a test flip a grant "while the user is in Settings".
    var onStatusRead:((PermissionKind,Int)->Void)?

    private(set) var statusReads:[PermissionKind]=[]
    private(set) var requested:[PermissionKind]=[]
    private(set) var openedKinds:[PermissionKind]=[]     // openSettings calls, whether or not they succeeded
    private(set) var openedURLs:[URL]=[]                  // URLs that actually opened
    private(set) var attemptedURLs:[URL]=[]
    private lazy var opener=PermissionSettingsOpener { [unowned self] url in
        self.attemptedURLs.append(url)
        guard self.openableURLs?.contains(url) ?? true else { return false }
        self.openedURLs.append(url); return true
    }

    init(os:OperatingSystemVersion=PermissionPolicy.minimumOS,_ statuses:[PermissionKind:PermissionStatus]=[:]) {
        osVersion=os; self.statuses=statuses
    }

    func status(_ kind:PermissionKind)->PermissionStatus {
        statusReads.append(kind)
        onStatusRead?(kind,statusReads.count)
        return statuses[kind] ?? .unknown
    }
    func request(_ kind:PermissionKind,completion:@escaping (PermissionStatus)->Void) {
        requested.append(kind)
        if let outcome=requestOutcome[kind] { statuses[kind]=outcome }
        completion(statuses[kind] ?? .unknown)
    }
    @discardableResult func openSettings(_ kind:PermissionKind)->Bool {
        openedKinds.append(kind)
        return opener.openPane(kind,os:osVersion)
    }
    func settingsURL(_ kind:PermissionKind)->URL? { PermissionSettingsLink.candidates(kind,os:osVersion).first }
}
