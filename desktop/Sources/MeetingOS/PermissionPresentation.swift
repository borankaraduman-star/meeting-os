import Foundation

/// Which button, wording and tone the permission cards show, decided in pure functions of `PermissionFlowState` /
/// `PermissionCardModel` (PermissionContract.swift). The views only draw what this returns and call no system API,
/// so every state × grant combination is a unit test instead of a click-through.

/// The four stops of the onboarding. The first three are the grants in `PermissionKind` order; `done` lists what
/// is left over.
enum PermissionStep: Int, CaseIterable, Hashable {
    case microphone, systemAudio, accessibility, done
    var kind:PermissionKind? {
        switch self { case .microphone: return .microphone; case .systemAudio: return .systemAudio; case .accessibility: return .accessibility; case .done: return nil }
    }
    static func step(_ kind:PermissionKind)->PermissionStep {
        switch kind { case .microphone: return .microphone; case .systemAudio: return .systemAudio; case .accessibility: return .accessibility }
    }
    var title:String {
        switch self { case .microphone: return "Mikrofon"; case .systemAudio: return "Toplantı sesi"; case .accessibility: return "Erişilebilirlik"; case .done: return "Tamam" }
    }
}

/// How one stop of the progress bar is drawn.
enum PermissionStepMark: String, Equatable {
    case granted, skipped, blockedBySystem, current, upcoming
    var symbol:String {
        switch self {
        case .granted: return "checkmark.circle.fill"
        case .skipped: return "minus.circle"
        case .blockedBySystem: return "lock.circle"
        case .current: return "circle.inset.filled"
        case .upcoming: return "circle"
        }
    }
    var spoken:String {
        switch self {
        case .granted: return "izin verildi"
        case .skipped: return "şimdilik geçildi"
        case .blockedBySystem: return "sistem tarafından kapalı"
        case .current: return "şu anki adım"
        case .upcoming: return "sırada"
        }
    }
}

/// One real button. Built only from a non-`.none` action, so a view that loops over these cannot draw a decoy.
struct PermissionCardAction: Equatable, Identifiable {
    let action:PermissionAction
    let kind:PermissionKind
    let label:String
    let isPrimary:Bool
    var id:String { kind.rawValue+"."+action.rawValue }
}

/// Everything one card draws, derived from the model + flow state.
struct PermissionCardContent: Equatable {
    let card:PermissionCardModel
    let badgeSymbol:String
    let badgeAccessibilityLabel:String
    let privacyNote:String
    let actions:[PermissionCardAction]
    /// After System Settings was opened for this grant: what to do there and that the status updates on its own.
    let settingsGuide:String?
    let relaunchExplanation:String?
}

enum PermissionPresentation {
    // MARK: wording
    static let settingsGuideText="Açılan pencerede Meeting OS’u açın, sonra buraya dönün; durum kendiliğinden güncellenir."
    static let reopenSetupLabel="İzin kurulumunu yeniden aç"
    static let finishLabel="Tamam"
    static let restrictedNote="Bu izni burada değiştiremezsiniz."

    /// The button text. `request` reads "İzin ver" here (the contract's neutral "İzin iste" is not shown).
    static func label(_ action:PermissionAction)->String {
        action == .request ? "İzin ver" : action.label
    }
    static func symbol(_ tone:PermissionTone)->String {
        switch tone {
        case .success: return "checkmark.circle.fill"
        case .waiting: return "hourglass"
        case .warning: return "exclamationmark.triangle.fill"
        case .error: return "xmark.octagon.fill"
        case .neutral: return "circle.dashed"
        }
    }
    /// The tone spoken, because colour alone is no signal for VoiceOver (or colour-blind eyes).
    static func toneWord(_ tone:PermissionTone)->String {
        switch tone {
        case .success: return "tamam"
        case .waiting: return "bekleniyor"
        case .warning: return "dikkat"
        case .error: return "sorun"
        case .neutral: return "bilgi"
        }
    }
    static func privacyNote(_ kind:PermissionKind)->String {
        switch kind {
        case .microphone: return "Mikrofon yalnız siz kaydı başlattığınızda dinlenir."
        case .systemAudio: return "Ekran görüntüsü alınmaz, saklanmaz; yalnız sistem sesi alınır."
        case .accessibility: return "Yalnız Zoom’un Sesi Aç/Kapat menü satırı okunur."
        }
    }
    static func badgeAccessibilityLabel(_ card:PermissionCardModel)->String {
        "\(card.title): \(card.statusLabel), \(toneWord(card.tone)). \(card.needLabel)."
    }

    // MARK: actions
    static func actions(_ card:PermissionCardModel)->[PermissionCardAction] {
        var out:[PermissionCardAction]=[]
        if card.primary != .none { out.append(PermissionCardAction(action:card.primary,kind:card.kind,label:label(card.primary),isPrimary:true)) }
        if card.secondary != .none,card.secondary != card.primary { out.append(PermissionCardAction(action:card.secondary,kind:card.kind,label:label(card.secondary),isPrimary:false)) }
        return out
    }
    static func isWaitingInSettings(_ kind:PermissionKind,_ s:PermissionFlowState)->Bool { s.pending==kind && s.phase == .waitingForSettings }

    static func content(_ kind:PermissionKind,_ s:PermissionFlowState)->PermissionCardContent {
        let card=PermissionCardModel.make(kind,state:s)
        // Only `needsRelaunch` is evidence that the grant is on and waits for a reopen. A suggested reopen while the
        // status still reads off is a guess (stale CGPreflight vs. switch never flipped), so the sentence is conditional.
        let offersRelaunch = card.primary == .relaunch || card.secondary == .relaunch
        let relaunch:String? = !offersRelaunch ? nil
            : s.snapshot.status(kind) == .needsRelaunch
            ? "Düğme uygulamayı kapatıp yeniden açar; izin yeniden açılıştan sonra geçerli olur."
            : "Anahtarı açtıysanız düğme uygulamayı kapatıp yeniden açar; macOS izni çoğu zaman ancak o zaman tanır. Anahtar kapalıysa yeniden açmak izni vermez."
        return PermissionCardContent(card:card,badgeSymbol:symbol(card.tone),badgeAccessibilityLabel:badgeAccessibilityLabel(card),
                                     privacyNote:privacyNote(kind),actions:actions(card),
                                     settingsGuide:isWaitingInSettings(kind,s) ? settingsGuideText : nil,
                                     relaunchExplanation:relaunch)
    }
    static func contents(_ s:PermissionFlowState)->[PermissionCardContent] { PermissionKind.allCases.map { content($0,s) } }

    // MARK: steps
    /// The grant the user is on, or `done` when nothing is left to do.
    static func currentStep(_ s:PermissionFlowState)->PermissionStep {
        if s.phase == .finished { return .done }
        return s.focus.map(PermissionStep.step) ?? .done
    }
    static func mark(_ step:PermissionStep,_ s:PermissionFlowState)->PermissionStepMark {
        let current=currentStep(s)
        guard let kind=step.kind else { return current == .done ? .current : .upcoming }
        let st=s.snapshot.status(kind)
        if st.isGranted { return .granted }
        if st.isFixedBySystem { return .blockedBySystem }
        if step == current { return .current }
        if s.skipped.contains(kind) { return .skipped }
        return .upcoming
    }
    static func marks(_ s:PermissionFlowState)->[(step:PermissionStep,mark:PermissionStepMark)] { PermissionStep.allCases.map { ($0,mark($0,s)) } }
    /// "Adım 2 / 4" — for the header.
    static func progressText(_ s:PermissionFlowState)->String { "Adım \(currentStep(s).rawValue+1) / \(PermissionStep.allCases.count)" }

    // MARK: done step
    /// Grants not on that the flow does not insist on, in order: what "Tamam" tells the user can be reopened later.
    static func missingOptional(_ s:PermissionFlowState)->[PermissionKind] {
        PermissionKind.allCases.filter { s.snapshot.need($0) != .required && !s.snapshot.status($0).isGranted }
    }
    static func doneTitle(_ s:PermissionFlowState)->String { s.snapshot.missingRequired.isEmpty ? "Kayda hazırsınız" : "Kayıt için eksik izin var" }
    static func doneDetail(_ s:PermissionFlowState)->String {
        let missing=s.snapshot.missingRequired
        if missing.isEmpty { return "Mikrofon ve sistem sesi açık; kayıt başlatabilirsiniz." }
        let names=missing.map { PermissionSettingsLink.paneName($0,os:s.snapshot.os) }.joined(separator:", ")
        return "Şu izinler kapalı olduğu için kayıt tam çalışmaz: \(names). Ayarlar → Sistem bölümünden kurulumu yeniden açabilirsiniz."
    }
    static func optionalLine(_ kind:PermissionKind,_ s:PermissionFlowState)->String {
        let st=s.snapshot.status(kind)
        let why = kind == .accessibility ? "yalnız “Zoom’u izle” modu için" : "isteğe bağlı"
        let state = st.isFixedBySystem ? (st == .restricted ? "yönetici kısıtlamış" : "bu macOS’ta yok") : (s.skipped.contains(kind) ? "geçildi" : "kapalı")
        return "\(PermissionCardModel.title(kind)) — \(state) (\(why))"
    }
    static let reopenHint="Eksik izinleri sonra Ayarlar → Sistem → “İzin kurulumunu yeniden aç”tan verebilirsiniz."
}
