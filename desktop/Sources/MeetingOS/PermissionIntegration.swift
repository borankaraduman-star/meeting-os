import AppKit
import SwiftUI

/// Where the permission onboarding meets the rest of the app (docs/IZIN_ONBOARDING.md): when it is put in front of
/// the user, what the Ayarlar list keeps, what a failed recording start says and how the app reopens itself.
/// Decisions are pure functions so each is a test; the views at the bottom only draw them.
enum PermissionIntegration {
    /// First launch (or a newer onboarding) on a Mac that cannot record yet — and never while a recording is on:
    /// a sheet that grabs the window mid-meeting is exactly the slowdown the product promises not to cause.
    /// `complete` is the stored completion (`PermissionFlowModel.isCompletionStored`), so “Şimdilik geç” is final.
    static func shouldPresentOnboarding(recording:Bool,complete:Bool,snapshot:PermissionSnapshot)->Bool {
        !recording && !complete && !snapshot.readyToRecord
    }

    /// The three grants now live in `PermissionSettingsSection`; the older “Kurulum durumu” list keeps every other
    /// row (calendar, reminders, notifications, services). Showing both would say the same thing twice, and in
    /// different words.
    static let ownedCheckIDs:Set<String>=["mic","screen","accessibility"]
    static func visibleChecks(_ checks:[SetupCheck])->[SetupCheck] { checks.filter { !ownedCheckIDs.contains($0.id) } }

    // MARK: Recording start

    /// The grant the capture helper reported as refused (`capture.permission`, written by `MeetingCapture`),
    /// microphone first. Evidence from the helper, not a guess from a preflight: system audio reads “off” on a Mac
    /// that was simply never asked, and the helper asks.
    static func deniedKind(_ capture:[String:Any])->PermissionKind? {
        guard let permission=capture["permission"] as? [String:Any] else { return nil }
        if permission["microphone"] as? String == "denied" { return .microphone }
        if permission["screen_audio"] as? String == "denied" { return .systemAudio }
        return nil
    }
    /// A microphone macOS has been told no to is certain from the app's own read, so it can be named before the
    /// helper even starts. Everything else waits for the helper (see `deniedKind`). Recording is never blocked.
    static func knownRefusal(_ snapshot:PermissionSnapshot)->PermissionKind? {
        snapshot.status(.microphone) == .denied ? .microphone : nil
    }

    struct Guidance:Equatable {
        let kind:PermissionKind
        let message:String
        let buttonLabel:String
    }
    /// The banner above the list while a recording lacks a grant: names the pane, offers the card. Gone as soon as
    /// the grant reads on (the app re-reads whenever it becomes active again), never shown for a granted one.
    static func guidance(_ kind:PermissionKind?,snapshot:PermissionSnapshot)->Guidance? {
        guard let kind, !snapshot.status(kind).isGranted else { return nil }
        let pane=PermissionSettingsLink.paneName(kind,os:snapshot.os)
        switch kind {
        case .microphone:
            return Guidance(kind:kind,message:"Mikrofon izni kapalı: sesiniz kaydedilemez. Sistem Ayarları → Gizlilik ve Güvenlik → \(pane) içinde Meeting OS’u açın.",
                            buttonLabel:"Mikrofon iznini aç")
        case .systemAudio:
            return Guidance(kind:kind,message:"“\(pane)” izni kapalı: karşı tarafın sesi kaydedilemez. Sistem Ayarları → Gizlilik ve Güvenlik → \(pane) içinde Meeting OS’u açın.",
                            buttonLabel:"Sistem sesi iznini aç")
        case .accessibility:
            return nil   // never needed for a recording to start (docs/IZIN_ONBOARDING.md b)
        }
    }

    // MARK: Welcome card

    struct WelcomeSummary:Equatable {
        let ready:Bool
        let title:String
        let detail:String
    }
    /// One honest line for the welcome screen: ready, or exactly which grants are still off.
    static func welcomeSummary(_ snapshot:PermissionSnapshot)->WelcomeSummary {
        let missing=snapshot.missingRequired
        if missing.isEmpty {
            return WelcomeSummary(ready:true,title:"İzinler tamam",detail:"Mikrofon ve toplantı sesi açık; kayıt başlatabilirsiniz.")
        }
        let names=missing.map { PermissionCardModel.title($0) }.joined(separator:" ve ")
        return WelcomeSummary(ready:false,title:"Kayıt için izin gerekli",
                              detail:"Şu izinler kapalı: \(names). Kuruluma başlayın; her adımda ne yapacağınız yazıyor.")
    }
}

// MARK: - Reopen

/// “Meeting OS’u yeniden aç”: a screen-recording grant only reaches a running process after it restarts. The app
/// cannot launch its own successor after it is gone, so a tiny shell waits for this pid to end and opens the bundle
/// again — bounded, so a quit that never completes does not leave a shell behind.
enum AppRelaunch {
    static func script(pid:Int32,appPath:String)->String {
        let quoted="'"+appPath.replacingOccurrences(of:"'",with:"'\\''")+"'"
        return "n=0; while kill -0 \(pid) 2>/dev/null && [ $n -lt 600 ]; do sleep 0.2; n=$((n+1)); done; /usr/bin/open -n \(quoted)"
    }
    @MainActor static func run() {
        let p=Process(); p.executableURL=URL(fileURLWithPath:"/bin/sh")
        p.arguments=["-c",script(pid:ProcessInfo.processInfo.processIdentifier,appPath:Bundle.main.bundlePath)]
        guard (try? p.run()) != nil else { return }   // could not even start the helper: stay open rather than quit into nothing
        NSApp.terminate(nil)                          // goes through applicationShouldTerminate: a running job finishes first
    }
}

// MARK: - Views

/// The onboarding as a sheet: the three cards, and at the bottom the way out that is always there.
struct PermissionOnboardingSheet:View {
    @ObservedObject var model:Model
    @ObservedObject var permissions:PermissionFlowModel
    init(model:Model) { self.model=model; permissions=model.permissions }
    var body:some View {
        let done=PermissionPresentation.currentStep(permissions.state) == .done
        VStack(spacing:0) {
            ScrollView { PermissionOnboardingView(state:permissions.state,send:permissions.handle).frame(maxWidth:.infinity) }
            Divider()
            HStack(alignment:.center,spacing:12) {
                VStack(alignment:.leading,spacing:2) {
                    Text(permissions.finishHint).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                    if permissions.relaunchRefused {
                        Text("Kayıt sürerken Meeting OS yeniden açılmaz; kayıt bitince tekrar deneyin.").font(.caption).foregroundStyle(.orange)
                    }
                }
                Spacer(minLength:8)
                if !done {
                    Button(permissions.finishLabel) { permissions.finish() }
                        .accessibilityIdentifier("permissionLater")
                }
            }.padding(.horizontal,24).padding(.vertical,12)
        }
        .frame(width:580,height:640)
        .onChange(of:permissions.state.phase) { _,phase in if phase == .finished { model.showPermissionOnboarding=false } }
        .onDisappear {
            // Esc or a click outside is the same answer as “Şimdilik geç” — except when a recording took the window
            // away: that is not the user's choice, so the onboarding stays available.
            if permissions.state.phase != .finished && !model.recording { permissions.finish() }
            permissions.stop()
        }
    }
}

/// Ayarlar → Sistem: the live rows. “İzin kurulumunu yeniden aç” goes through the app (it has to close Ayarlar
/// first: two sheets on one window never both show).
struct PermissionSettingsBlock:View {
    @ObservedObject var model:Model
    @ObservedObject var permissions:PermissionFlowModel
    init(model:Model) { self.model=model; permissions=model.permissions }
    var body:some View {
        PermissionSettingsSection(state:permissions.state) { event in
            if event == .reopen { model.presentPermissionOnboarding(reopen:true) } else { permissions.handle(event) }
        }
        .padding(14).meetingCard()
        .task { permissions.refresh() }
    }
}

/// Welcome screen: what is still off, and the way into the onboarding once it was dismissed.
struct WelcomePermissionCard:View {
    @ObservedObject var model:Model
    @ObservedObject var permissions:PermissionFlowModel
    init(model:Model) { self.model=model; permissions=model.permissions }
    var body:some View {
        let summary=PermissionIntegration.welcomeSummary(permissions.state.snapshot)
        HStack(alignment:.top,spacing:12) {
            Image(systemName:summary.ready ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                .foregroundStyle(summary.ready ? MeetingStyle.accent : Color.orange).font(.title3).accessibilityHidden(true)
            VStack(alignment:.leading,spacing:3) {
                Text(summary.title).font(.headline)
                Text(summary.detail).font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
            }
            Spacer(minLength:8)
            if !summary.ready {
                Button("İzin kurulumunu aç") { model.presentPermissionOnboarding(reopen:false) }
                    .buttonStyle(.borderedProminent).accessibilityIdentifier("welcomePermissionButton")
            }
        }
        .padding(16).meetingCard().frame(maxWidth:640)
        .accessibilityElement(children:.contain).accessibilityIdentifier("welcomePermissions")
        .task { permissions.refresh() }
    }
}

/// The recording-start error path: a banner under the sidebar controls that names the missing grant and opens its card.
struct PermissionGuidanceBanner:View {
    @ObservedObject var model:Model
    @ObservedObject var permissions:PermissionFlowModel
    init(model:Model) { self.model=model; permissions=model.permissions }
    var body:some View {
        if let g=PermissionIntegration.guidance(model.permissionGuidance,snapshot:permissions.state.snapshot) {
            HStack(alignment:.top,spacing:10) {
                Image(systemName:"lock.trianglebadge.exclamationmark.fill").foregroundStyle(.orange)
                VStack(alignment:.leading,spacing:6) {
                    Text(g.message).font(.callout).fixedSize(horizontal:false,vertical:true)
                    Button(g.buttonLabel) { model.presentPermissionOnboarding(reopen:true) }
                        .controlSize(.small).accessibilityIdentifier("permissionGuidanceButton")
                }
                Spacer(minLength:8)
                Button { model.permissionGuidance=nil } label: { Image(systemName:"xmark.circle.fill").foregroundStyle(.secondary) }
                    .buttonStyle(.plain).accessibilityLabel("İzin uyarısını kapat")
            }
            .padding(16).background(.orange.opacity(0.12)).accessibilityIdentifier("permissionGuidance")
        }
    }
}
