import Foundation

/// The shared contract of the permission onboarding (docs/IZIN_ONBOARDING.md): the three grants a recording
/// touches, what each one is FOR on this Mac, and one pure reducer that walks the user through them. Types,
/// a protocol and pure logic only — no AppKit, no AVFoundation, no TCC. The native provider and the SwiftUI
/// cards are written against this file in parallel, and the tests drive it with a fake provider and synthetic
/// transitions, so nothing here may ever touch a real permission. It grows only by addition: a renamed case
/// breaks the steps coding against it.

// MARK: - Vocabulary

/// Ordered: the flow offers them in this order, because the microphone is the one macOS can ask about in-app
/// and the other two end in System Settings anyway.
enum PermissionKind: String, CaseIterable, Codable, Hashable, Sendable {
    case microphone, systemAudio, accessibility

    /// The anchor of the Privacy pane in `x-apple.systempreferences:` URLs. System audio is the Screen Recording
    /// entry: ScreenCaptureKit is how the helper hears the other side, and macOS ties system audio to that grant.
    var paneAnchor:String {
        switch self {
        case .microphone: return "Privacy_Microphone"
        case .systemAudio: return "Privacy_ScreenCapture"
        case .accessibility: return "Privacy_Accessibility"
        }
    }
    /// macOS asks in-app only for the microphone. The screen and Accessibility prompts return at once and point
    /// at System Settings, where the switch is flicked by hand — so after "asking" the flow waits there.
    var grantedInSettings:Bool { self != .microphone }
    /// The first macOS where the API exists at all: microphone TCC (10.14), ScreenCaptureKit audio (13.0), AX
    /// (always). The app itself needs 15.0 (`PermissionPolicy.minimumOS`); this only keeps `unsupported` honest.
    var minimumOS:OperatingSystemVersion {
        switch self {
        case .microphone: return OperatingSystemVersion(majorVersion:10,minorVersion:14,patchVersion:0)
        case .systemAudio: return OperatingSystemVersion(majorVersion:13,minorVersion:0,patchVersion:0)
        case .accessibility: return OperatingSystemVersion(majorVersion:10,minorVersion:9,patchVersion:0)
        }
    }
}

/// What the provider could establish. `needsRelaunch` is reported only on evidence (e.g. the capture helper
/// was granted while this process's preflight still says no): CGPreflightScreenCaptureAccess can keep answering
/// false until the app is reopened. A bare `false` is `denied`, never a guess that it is secretly granted.
enum PermissionStatus: String, Codable, Hashable, Sendable {
    case authorized, denied, notDetermined, restricted, unknown, unsupported, needsRelaunch
    var isGranted:Bool { self == .authorized }
    /// Nothing the user can press changes these: an MDM lock, or an OS without the API.
    var isFixedBySystem:Bool { self == .restricted || self == .unsupported }
}

/// `conditional`: needed only for one feature (Accessibility ↔ "Zoom’u izle"); the card says which, and a
/// missing conditional grant never blocks recording or completion.
enum PermissionNeed: String, Codable, Hashable, Sendable { case required, optional, conditional }

/// What a card's button does. `none` means no button — never a disabled decoy that looks like it would work.
enum PermissionAction: String, Codable, Hashable, Sendable {
    case request, openSettings, recheck, skip, relaunch, none
    var label:String {
        switch self {
        case .request: return "İzin iste"
        case .openSettings: return "Sistem Ayarları’nı aç"
        case .recheck: return "Yeniden kontrol et"
        case .skip: return "Şimdilik geç"
        case .relaunch: return "Meeting OS’u yeniden aç"
        case .none: return ""
        }
    }
}

/// Badge colour of a card, mapped to the app's palette by the view.
enum PermissionTone: String, Codable, Hashable, Sendable { case success, waiting, warning, error, neutral }

// MARK: - Provider

/// The only door to the real system. The native implementation reads TCC through the public APIs and opens
/// System Settings; tests hand in a fake. Contract:
/// - `status` is cheap and side-effect free (no prompt) — it is polled.
/// - `request` may show a macOS prompt, so it is called ONLY from a user's click; `completion` runs on the main
///   queue with the status as it stands afterwards (for screen/AX that is usually still `denied`).
/// - `openSettings` opens the exact pane, falls back to the general Privacy pane, and returns false only when
///   neither could be opened.
/// - `osVersion` is injected (default: the running OS) so every macOS branch is a test, not a VM.
protocol PermissionProviding {
    var osVersion:OperatingSystemVersion { get }
    func status(_ kind:PermissionKind)->PermissionStatus
    func request(_ kind:PermissionKind,completion:@escaping (PermissionStatus)->Void)
    @discardableResult func openSettings(_ kind:PermissionKind)->Bool
    func settingsURL(_ kind:PermissionKind)->URL?
}

extension PermissionProviding {
    func settingsURL(_ kind:PermissionKind)->URL? { PermissionSettingsLink.url(kind,os:osVersion) }
    /// Every kind read once. `unsupported` comes from the OS version before the provider is even asked.
    func snapshot(micMode:String)->PermissionSnapshot {
        var statuses:[PermissionKind:PermissionStatus]=[:]
        for kind in PermissionKind.allCases { statuses[kind]=PermissionFlow.supported(kind,os:osVersion) ? status(kind) : .unsupported }
        return PermissionSnapshot(statuses:statuses,micMode:micMode,os:osVersion)
    }
}

// MARK: - System Settings links

/// Where each grant lives, per macOS. The `com.apple.preference.security?Privacy_*` form is the one this app has
/// used since 1.0 (`SetupStatus.openPane`) and still lands on the right pane on 13–15; the fallback is the general
/// Privacy & Security pane. Constants, so the evidence step can tune them without touching the reducer.
enum PermissionSettingsLink {
    static let legacyPrefix="x-apple.systempreferences:com.apple.preference.security?"
    static let privacyPane13="x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension"
    static let privacyPaneLegacy="x-apple.systempreferences:com.apple.preference.security?Privacy"

    static func url(_ kind:PermissionKind,os:OperatingSystemVersion)->URL? {
        guard PermissionFlow.supported(kind,os:os) else { return nil }
        return URL(string:legacyPrefix+kind.paneAnchor)
    }
    static func fallbackURL(os:OperatingSystemVersion)->URL? { URL(string:os.majorVersion>=13 ? privacyPane13 : privacyPaneLegacy) }
    /// The pane's own name, as the user will see it in the sidebar list. macOS 15 renamed Screen Recording when
    /// it put system audio next to it — the old name would send the user hunting for a row that is not there.
    static func paneName(_ kind:PermissionKind,os:OperatingSystemVersion)->String {
        switch kind {
        case .microphone: return "Mikrofon"
        case .systemAudio: return os.majorVersion>=15 ? "Ekran ve Sistem Sesi Kaydı" : "Ekran Kaydı"
        case .accessibility: return "Erişilebilirlik"
        }
    }
    /// The route spelled out for a footnote, the fallback when no URL opens.
    static func path(_ kind:PermissionKind,os:OperatingSystemVersion)->String {
        let root=os.majorVersion>=13 ? "Sistem Ayarları → Gizlilik ve Güvenlik" : "Sistem Tercihleri → Güvenlik ve Gizlilik → Gizlilik"
        return root+" → "+paneName(kind,os:os)
    }
}

// MARK: - Policy

/// Tunable numbers and keys. The poll bounds are a first guess until the Granola evidence step pins them: one
/// read a second while System Settings is in front, two minutes at most — long enough to find a switch, short
/// enough that a forgotten pane never leaves a timer running.
enum PermissionPolicy {
    static let pollInterval:TimeInterval=1.0
    static let pollLimit=120
    /// Bump to show the onboarding once more to everybody (a new grant, a reworded step).
    static let onboardingVersion=1
    /// UserDefaults: the `onboardingVersion` the user last finished (missing = 0, never finished).
    static let completedVersionKey="permissionOnboardingCompletedVersion"
    /// LSMinimumSystemVersion, and the first macOS where the helper's `SCStreamConfiguration.captureMicrophone` exists.
    static let minimumOS=OperatingSystemVersion(majorVersion:15,minorVersion:0,patchVersion:0)

    /// Microphone and system audio are the recording itself. Accessibility only reads Zoom's mute row
    /// (`ZoomMute`), so it matters only in "Zoom’u izle"; without it the gate never opens and finalize keeps the
    /// whole microphone track (cloud_finalize: a gate that never opened is not applied) — nothing is lost.
    static func need(_ kind:PermissionKind,micMode:String)->PermissionNeed {
        switch kind {
        case .microphone, .systemAudio: return .required
        case .accessibility: return MicGate.normalize(micMode)=="zoom" ? .conditional : .optional
        }
    }
    /// First launch, or a newer onboarding: show it — unless every required grant is already there (a Mac that
    /// has been recording for months does not need a welcome tour of switches that are already on).
    static func shouldPresent(storedVersion:Int,snapshot:PermissionSnapshot)->Bool {
        storedVersion<onboardingVersion && !snapshot.readyToRecord
    }
}

// MARK: - Snapshot

/// Every status read at one moment, with what decides the needs (mic mode) and the wording (OS version).
struct PermissionSnapshot: Equatable {
    var statuses:[PermissionKind:PermissionStatus]
    var micMode:String
    var os:OperatingSystemVersion

    init(statuses:[PermissionKind:PermissionStatus]=[:],micMode:String="zoom",os:OperatingSystemVersion=PermissionPolicy.minimumOS) {
        self.statuses=statuses; self.micMode=micMode; self.os=os
    }
    static func == (a:PermissionSnapshot,b:PermissionSnapshot)->Bool {
        a.statuses==b.statuses && a.micMode==b.micMode && a.os.majorVersion==b.os.majorVersion
            && a.os.minorVersion==b.os.minorVersion && a.os.patchVersion==b.os.patchVersion
    }
    /// A kind never read is `unknown`, not `denied`: nobody asked yet.
    func status(_ kind:PermissionKind)->PermissionStatus { statuses[kind] ?? .unknown }
    func need(_ kind:PermissionKind)->PermissionNeed { PermissionPolicy.need(kind,micMode:micMode) }
    var readyToRecord:Bool { status(.microphone).isGranted && status(.systemAudio).isGranted }
    var missingRequired:[PermissionKind] { PermissionKind.allCases.filter { need($0) == .required && !status($0).isGranted } }
    func updating(_ kind:PermissionKind,_ status:PermissionStatus)->PermissionSnapshot {
        var copy=self; copy.statuses[kind]=status; return copy
    }
}

// MARK: - Flow

enum PermissionFlowPhase: String, Codable, Hashable, Sendable {
    /// `requesting`: a macOS prompt may be on screen. `waitingForSettings`: System Settings was opened for
    /// `pending` and the flow polls until the grant shows, the user comes back, or `pollLimit` runs out.
    case idle, active, requesting, waitingForSettings, finished
}

/// Side effects the driver performs after a reduce, in order. The reducer never does them itself.
enum PermissionEffect: Equatable {
    case refresh                          // read a new snapshot, send `.refreshed`
    case request(PermissionKind)          // provider.request → `.requestFinished`
    case openSettings(PermissionKind)     // provider.openSettings; false → `.settingsOpenFailed`
    case relaunch                         // reopen the app — the driver refuses while a recording runs
    case persistCompletion                // store `onboardingVersion` under `completedVersionKey`
}

/// One-line explanation shown on the card it concerns, cleared by the next action.
enum PermissionNotice: Equatable {
    case settingsUnavailable(PermissionKind)
    case noChangeSeen(PermissionKind)
    case requestDenied(PermissionKind)
    var kind:PermissionKind {
        switch self { case .settingsUnavailable(let k), .noChangeSeen(let k), .requestDenied(let k): return k }
    }
}

struct PermissionFlowState: Equatable {
    var phase:PermissionFlowPhase = .idle
    var snapshot:PermissionSnapshot
    /// The card the flow points at: the first grant still to do. nil = nothing left to do (finish is offered).
    var focus:PermissionKind?
    /// The grant a prompt or a System Settings visit is about.
    var pending:PermissionKind?
    var skipped:Set<PermissionKind>=[]
    /// Screen grant switched on but this process may not see it until reopened: offered, never assumed.
    var relaunchSuggested:Set<PermissionKind>=[]
    var pollsLeft=0
    /// The app became active again while waiting: the user has been to System Settings and back.
    var returnedFromSettings=false
    var notice:PermissionNotice?
    /// `.finish` was reached in this run (the driver persists it through `persistCompletion`).
    var completed=false
    /// What the driver must do now; replaced by every reduce.
    var effects:[PermissionEffect]=[]

    init(snapshot:PermissionSnapshot=PermissionSnapshot()) { self.snapshot=snapshot }
    var isPolling:Bool { phase == .waitingForSettings && pollsLeft>0 }
    var allRequiredGranted:Bool { snapshot.missingRequired.isEmpty }
}

enum PermissionFlowEvent: Equatable {
    case appear
    case primaryTapped(PermissionKind)
    case requestFinished(PermissionKind,PermissionStatus)
    case returnedFromSettings
    case pollTick
    case skip(PermissionKind)
    case finish
    case reopen
    // Additions the driver needs: the answer to `.refresh`, any card button, and a pane that would not open.
    case refreshed(PermissionSnapshot)
    case actionTapped(PermissionAction,PermissionKind)
    case settingsOpenFailed(PermissionKind)
}

enum PermissionFlow {
    static func supported(_ kind:PermissionKind,os:OperatingSystemVersion)->Bool {
        let m=kind.minimumOS
        return (os.majorVersion,os.minorVersion,os.patchVersion) >= (m.majorVersion,m.minorVersion,m.patchVersion)
    }

    /// First grant still to do, in order. A pending one keeps the focus; skipped, granted and system-fixed ones
    /// (MDM, old OS) never take it — a focus with no possible action would leave the user stuck.
    static func nextFocus(_ s:PermissionFlowState)->PermissionKind? {
        if let p=s.pending { return p }
        return PermissionKind.allCases.first { k in
            let st=s.snapshot.status(k)
            return !st.isGranted && !st.isFixedBySystem && !s.skipped.contains(k)
        }
    }

    static func primaryAction(_ kind:PermissionKind,in s:PermissionFlowState)->PermissionAction {
        if s.pending==kind && s.phase == .requesting { return .none }          // macOS is asking; one question at a time
        if s.pending==kind && s.phase == .waitingForSettings { return .recheck }
        switch s.snapshot.status(kind) {
        case .authorized, .restricted, .unsupported: return .none
        case .notDetermined: return .request
        case .denied: return .openSettings
        case .needsRelaunch: return .relaunch
        case .unknown: return .recheck
        }
    }

    static func secondaryAction(_ kind:PermissionKind,in s:PermissionFlowState)->PermissionAction {
        let st=s.snapshot.status(kind)
        if st.isGranted || st.isFixedBySystem { return .none }
        if s.pending==kind && s.phase == .waitingForSettings { return s.relaunchSuggested.contains(kind) ? .relaunch : .openSettings }
        if s.pending==kind && s.phase == .requesting { return .none }
        if s.relaunchSuggested.contains(kind) && st != .needsRelaunch { return .relaunch }
        if s.snapshot.need(kind) != .required && !s.skipped.contains(kind) { return .skip }
        return st == .denied ? .recheck : .none
    }

    /// Back to an idle-but-active flow: no prompt open, no pane watched.
    private static func settle(_ s:inout PermissionFlowState) {
        s.pending=nil; s.pollsLeft=0; s.returnedFromSettings=false
        if s.phase == .requesting || s.phase == .waitingForSettings { s.phase = .active }
    }
    private static func startWaiting(_ s:inout PermissionFlowState,_ kind:PermissionKind) {
        s.phase = .waitingForSettings; s.pending=kind; s.pollsLeft=PermissionPolicy.pollLimit; s.returnedFromSettings=false
    }

    static func reduce(_ state:PermissionFlowState,_ event:PermissionFlowEvent)->PermissionFlowState {
        var s=state
        s.effects=[]
        switch event {
        case .appear:
            if s.phase == .idle { s.phase = .active }
            s.effects=[.refresh]
        case .reopen:
            // From Settings → Sistem: everything offered again, statuses re-read. The stored completion stays;
            // reopening is a look, not an undo. Relaunch hints stay too — only a relaunch clears a stale preflight.
            s.phase = .active; s.completed=false; s.skipped=[]; s.notice=nil
            settle(&s)
            s.effects=[.refresh]
        case .refreshed(let snap):
            s.snapshot=snap
            s.relaunchSuggested=s.relaunchSuggested.filter { !snap.status($0).isGranted }
            if let k=s.pending {
                if snap.status(k).isGranted || snap.status(k).isFixedBySystem || snap.status(k) == .needsRelaunch { settle(&s); s.notice=nil }
                else if s.phase == .waitingForSettings {
                    // Back from System Settings and the screen grant still reads off: that is exactly what a stale
                    // CGPreflight looks like, so a relaunch is offered — as an option, the badge stays truthful.
                    if s.returnedFromSettings && k == .systemAudio { s.relaunchSuggested.insert(k) }
                    if s.pollsLeft==0 { settle(&s); s.notice = .noChangeSeen(k) }
                }
            }
        case .pollTick:
            guard s.isPolling else { break }
            s.pollsLeft-=1
            s.effects=[.refresh]
        case .returnedFromSettings:
            // didBecomeActive: re-read whatever the phase — the user may have flicked a switch on their own.
            if s.phase == .waitingForSettings { s.returnedFromSettings=true }
            s.effects=[.refresh]
        case .primaryTapped(let k):
            return reduce(s,.actionTapped(primaryAction(k,in:s),k))
        case .actionTapped(let action,let k):
            guard s.phase != .requesting else { break }
            if s.phase == .idle || s.phase == .finished { s.phase = .active }
            switch action {
            case .request:
                s.phase = .requesting; s.pending=k; s.notice=nil; s.effects=[.request(k)]
            case .openSettings:
                startWaiting(&s,k); s.notice=nil; s.effects=[.openSettings(k)]
            case .recheck:
                s.notice=nil; s.effects=[.refresh]
            case .skip:
                return reduce(s,.skip(k))
            case .relaunch:
                s.effects=[.relaunch]
            case .none:
                break
            }
        case .requestFinished(let k,let st):
            // A late answer is still evidence: the status is recorded even when the flow has moved on.
            s.snapshot=s.snapshot.updating(k,st)
            if s.pending==k && s.phase == .requesting {
                if st.isGranted || st.isFixedBySystem { settle(&s) }
                else if k.grantedInSettings { startWaiting(&s,k) }   // the OS prompt pointed at System Settings
                else { settle(&s); if st == .denied { s.notice = .requestDenied(k) } }
                // Accessibility's prompt only lists the app; the pane is opened here so a failed open is recoverable.
                if s.phase == .waitingForSettings && k == .accessibility { s.effects=[.openSettings(k),.refresh]; break }
            }
            s.effects=[.refresh]
        case .skip(let k):
            s.skipped.insert(k)
            if s.pending==k { settle(&s) }
            if s.notice?.kind==k { s.notice=nil }
        case .settingsOpenFailed(let k):
            if s.pending==k { settle(&s) }
            s.notice = .settingsUnavailable(k)
        case .finish:
            settle(&s)
            s.phase = .finished; s.completed=true; s.notice=nil
            s.effects=[.persistCompletion]
        }
        s.focus=nextFocus(s)
        return s
    }
}

// MARK: - Card

/// Everything a card shows, decided here so the onboarding and the Settings card can never word the same state
/// two ways. The badge is always the real status: a skipped or optional grant is never painted as given.
struct PermissionCardModel: Equatable, Identifiable {
    var id:PermissionKind { kind }
    let kind:PermissionKind
    let title:String
    let reason:String
    let statusLabel:String
    let tone:PermissionTone
    let need:PermissionNeed
    let needLabel:String
    let primary:PermissionAction
    let secondary:PermissionAction
    let footnote:String
    let isFocused:Bool
    /// A prompt is open or the pane is being watched: the view shows a spinner next to the badge.
    let isBusy:Bool

    var primaryLabel:String { primary.label }
    var secondaryLabel:String { secondary.label }

    static func title(_ kind:PermissionKind)->String {
        switch kind {
        case .microphone: return "Mikrofon"
        case .systemAudio: return "Sistem sesi (karşı tarafın sesi)"
        case .accessibility: return "Erişilebilirlik (Zoom’daki sessiz durumu)"
        }
    }
    static func reason(_ kind:PermissionKind,need:PermissionNeed)->String {
        switch kind {
        case .microphone:
            return "Toplantıda kendi sesinizi kaydetmek için gerekir. Mikrofon yalnız kayıt sürerken kullanılır."
        case .systemAudio:
            return "Karşı tarafın sesi (Zoom’dan hoparlöre giden ses) macOS’ta yalnız bu izinle alınabilir. Ekran görüntüsü alınmaz, saklanmaz."
        case .accessibility:
            let what="Meeting OS yalnız Zoom’un Toplantı menüsündeki “Sesi Aç / Sesi Kapat” satırını okur; tuş vuruşu ya da ekran içeriği okunmaz. Kısayollar (⌃⌥R, ⌃⌥V) bu izin olmadan da çalışır."
            return need == .conditional
                ? what+" “Zoom’u izle” modunda sessizdeyken konuştuklarınızı kayıttan ayırmak için gerekir; izin yoksa kendi sesiniz kaybolmaz, tamamı kaydedilir."
                : what+" Şu anki mikrofon modunda kullanılmaz; isteğe bağlıdır."
        }
    }
    static func needLabel(_ need:PermissionNeed)->String {
        switch need {
        case .required: return "Gerekli"
        case .optional: return "İsteğe bağlı"
        case .conditional: return "“Zoom’u izle” modunda gerekli"
        }
    }

    static func make(_ kind:PermissionKind,state s:PermissionFlowState)->PermissionCardModel {
        let os=s.snapshot.os, st=s.snapshot.status(kind), need=s.snapshot.need(kind)
        let path=PermissionSettingsLink.path(kind,os:os)
        let requesting=s.pending==kind && s.phase == .requesting
        let waiting=s.pending==kind && s.phase == .waitingForSettings
        let skipped=s.skipped.contains(kind) && !st.isGranted

        var label:String, tone:PermissionTone
        switch st {
        case .authorized: label="İzin verildi"; tone = .success
        case .denied: label="Kapalı"; tone = need == .required ? .error : .warning
        case .notDetermined: label="Henüz sorulmadı"; tone = .neutral
        case .restricted: label="Yönetici kısıtlamış"; tone = need == .required ? .error : .warning
        case .unknown: label="Okunamadı"; tone = .warning
        case .unsupported: label="Bu macOS’ta yok"; tone = .neutral
        case .needsRelaunch: label="Yeniden açılış gerekiyor"; tone = .warning
        }
        if requesting { label="macOS soruyor…"; tone = .waiting }
        else if waiting { label="Sistem Ayarları’nda bekleniyor…"; tone = .waiting }
        else if skipped { label+=" · geçildi"; tone = .neutral }

        var notes:[String]=[]
        if let n=s.notice, n.kind==kind {
            switch n {
            case .settingsUnavailable: notes.append("Sistem Ayarları açılamadı. Elle açın: \(path).")
            case .noChangeSeen: notes.append("Değişiklik görülmedi. \(path) içinde Meeting OS’un anahtarını açtıysanız “Yeniden kontrol et”e basın.")
            case .requestDenied: notes.append("İzin verilmedi. macOS artık yalnız \(path) içinden açmanıza izin verir.")
            }
        }
        if waiting {
            notes.append("\(path) içinde Meeting OS’un anahtarını açın; listede yoksa alttaki + ile ekleyin. Buraya döndüğünüzde kendiliğinden kontrol edilir.")
        } else if s.notice?.kind != kind {
            switch st {
            case .denied: notes.append("\(path) içinde Meeting OS’u açın.")
            case .restricted: notes.append("Bu izin cihaz yönetimi tarafından kilitlenmiş; değiştirmek için BT yöneticinize başvurun.")
            case .unsupported: notes.append("Meeting OS macOS 15 ve sonrasını gerektirir.")
            case .unknown: notes.append("Durum okunamadı; “Yeniden kontrol et” ile tekrar deneyin.")
            case .needsRelaunch: notes.append("macOS bu izni Meeting OS yeniden açılınca uygular. Kayıt sürerken yeniden açılmaz.")
            case .authorized, .notDetermined: break
            }
        }
        if s.relaunchSuggested.contains(kind) && st != .needsRelaunch && !st.isGranted {
            notes.append("Anahtarı açtıysanız macOS bunu çoğu zaman Meeting OS yeniden açılınca tanır.")
        }
        return PermissionCardModel(kind:kind,title:title(kind),reason:reason(kind,need:need),statusLabel:label,tone:tone,
                                   need:need,needLabel:needLabel(need),primary:PermissionFlow.primaryAction(kind,in:s),
                                   secondary:PermissionFlow.secondaryAction(kind,in:s),footnote:notes.joined(separator:" "),
                                   isFocused:s.focus==kind,isBusy:requesting || waiting)
    }
    static func all(_ s:PermissionFlowState)->[PermissionCardModel] { PermissionKind.allCases.map { make($0,state:s) } }
}
