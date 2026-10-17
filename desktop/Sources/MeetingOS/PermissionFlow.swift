import AppKit
import Foundation

/// Cancels a repeating tick. The default schedules a `Timer`; tests hand in a closure they fire by hand.
typealias PermissionTicker=(_ interval:TimeInterval,_ fire:@escaping @MainActor ()->Void)->(()->Void)

/// The driver of `PermissionFlow.reduce`: owns the state, performs the effects against a provider, re-reads when
/// the app becomes active again, polls (bounded) while System Settings is being watched, and stores completion.
/// The views bind to `state`/`cards`; nothing here knows SwiftUI beyond `ObservableObject`.
@MainActor final class PermissionFlowModel:ObservableObject {
    @Published private(set) var state:PermissionFlowState
    /// The reopen/relaunch could not run because a recording is on; the view says so.
    @Published private(set) var relaunchRefused=false

    private let provider:PermissionProviding
    private let defaults:UserDefaults
    private let center:NotificationCenter
    private let makeTicker:PermissionTicker
    private var relaunch:()->Void
    private var isRecording:()->Bool
    private var micMode:String
    private var cancelTicker:(()->Void)?
    private var observer:NSObjectProtocol?

    static let timerTicker:PermissionTicker={ interval,fire in
        let timer=Timer.scheduledTimer(withTimeInterval:interval,repeats:true) { _ in MainActor.assumeIsolated { fire() } }
        return { timer.invalidate() }
    }

    init(provider:PermissionProviding,micMode:String="zoom",defaults:UserDefaults = .standard,
         center:NotificationCenter = .default,ticker:PermissionTicker?=nil,
         isRecording:@escaping ()->Bool={ false },relaunch:@escaping ()->Void={}) {
        self.provider=provider; self.micMode=micMode; self.defaults=defaults; self.center=center
        makeTicker=ticker ?? Self.timerTicker; self.isRecording=isRecording; self.relaunch=relaunch
        state=PermissionFlowState(snapshot:provider.snapshot(micMode:micMode))
        state.focus=PermissionFlow.nextFocus(state)
        observer=center.addObserver(forName:NSApplication.didBecomeActiveNotification,object:nil,queue:.main) { [weak self] _ in
            MainActor.assumeIsolated { self?.send(.returnedFromSettings) }
        }
    }
    deinit {
        // `deinit` is nonisolated: only the thread-safe teardown happens here. `stop()` is the explicit path for views.
        if let observer { center.removeObserver(observer) }
        cancelTicker?()
    }

    // MARK: Events

    /// The one entry for views and the app: every card button, the Settings rows and the reopen all come through here.
    func handle(_ event:PermissionFlowEvent) { send(event) }
    /// The owner of the model (the app `Model`) hands in what only it knows once it exists: is a recording on,
    /// and how to reopen the app. Additive to `init`, so the model can be built before its owner is.
    func attach(isRecording:@escaping ()->Bool,relaunch:@escaping ()->Void) { self.isRecording=isRecording; self.relaunch=relaunch }
    /// Re-read every status now (cheap, no prompt): Settings opening, the welcome card, the setup list.
    @discardableResult func refresh()->PermissionSnapshot { send(.refreshed(provider.snapshot(micMode:micMode))); return state.snapshot }
    func appear() { send(.appear) }
    func tapPrimary(_ kind:PermissionKind) { send(.primaryTapped(kind)) }
    func tapSecondary(_ kind:PermissionKind) { send(.actionTapped(PermissionFlow.secondaryAction(kind,in:state),kind)) }
    func skip(_ kind:PermissionKind) { send(.skip(kind)) }
    /// "Bitti" when every required grant is on, “Şimdilik geç” when not: both end the onboarding and remember it.
    func finish() { send(.finish) }
    /// Settings → Sistem → “İzinleri yeniden göster”: everything offered again; the stored completion stays.
    func reopen() { send(.reopen) }
    /// The mic mode decides whether Accessibility is `conditional` or `optional`.
    func setMicMode(_ mode:String) { micMode=mode; send(.refreshed(provider.snapshot(micMode:mode))) }
    /// Leaves nothing running: the view calls it when it goes away.
    func stop() { stopTicker() }

    // MARK: Derived

    var cards:[PermissionCardModel] { PermissionCardModel.all(state) }
    var allRequiredGranted:Bool { state.allRequiredGranted }
    var finishLabel:String { allRequiredGranted ? "Bitti" : "Şimdilik geç" }
    /// Why “Şimdilik geç” is not a failure: the card badges keep telling the truth, and recording re-checks.
    var finishHint:String {
        allRequiredGranted ? "Gerekli izinlerin hepsi açık."
            : "Eksik izinler Ayarlar → Sistem bölümünden istediğiniz zaman tamamlanabilir; kayıt başlamadan önce yeniden kontrol edilir."
    }
    var isPolling:Bool { cancelTicker != nil }
    var storedVersion:Int { defaults.integer(forKey:PermissionPolicy.completedVersionKey) }
    var isCompletionStored:Bool { storedVersion>=PermissionPolicy.onboardingVersion }
    /// Should the app put the onboarding in front of the user now?
    var shouldPresent:Bool { PermissionPolicy.shouldPresent(storedVersion:storedVersion,snapshot:state.snapshot) }

    // MARK: Driver

    private func send(_ event:PermissionFlowEvent) {
        state=PermissionFlow.reduce(state,event)
        let effects=state.effects
        for effect in effects { perform(effect) }
        syncTicker()
    }

    private func perform(_ effect:PermissionEffect) {
        switch effect {
        case .refresh:
            send(.refreshed(provider.snapshot(micMode:micMode)))
        case .request(let kind):
            provider.request(kind) { [weak self] status in
                DispatchQueue.main.async { MainActor.assumeIsolated { self?.send(.requestFinished(kind,status)) } }
            }
        case .openSettings(let kind):
            if !provider.openSettings(kind) { send(.settingsOpenFailed(kind)) }
        case .relaunch:
            relaunchRefused=isRecording()
            if !relaunchRefused { relaunch() }
        case .persistCompletion:
            defaults.set(PermissionPolicy.onboardingVersion,forKey:PermissionPolicy.completedVersionKey)
        }
    }

    private func syncTicker() {
        if state.isPolling { if cancelTicker==nil { startTicker() } } else { stopTicker() }
    }
    private func startTicker() {
        cancelTicker=makeTicker(PermissionPolicy.pollInterval) { [weak self] in self?.send(.pollTick) }
    }
    private func stopTicker() { cancelTicker?(); cancelTicker=nil }
}
