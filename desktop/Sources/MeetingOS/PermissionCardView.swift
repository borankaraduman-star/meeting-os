import SwiftUI

/// Colour of a badge. The symbol and the text carry the meaning too; this only reinforces it.
extension PermissionTone {
    var color:Color {
        switch self {
        case .success: return MeetingStyle.accent
        case .waiting: return .blue
        case .warning: return .orange
        case .error: return .red
        case .neutral: return .secondary
        }
    }
}

/// Status pill: colour + SF Symbol + text, read out as one label.
struct PermissionBadge:View {
    let content:PermissionCardContent
    var body:some View {
        let tone=content.card.tone
        HStack(spacing:5) {
            if content.card.isBusy { ProgressView().controlSize(.mini) } else { Image(systemName:content.badgeSymbol).imageScale(.small) }
            Text(content.card.statusLabel).font(.caption.weight(.semibold))
        }
        .foregroundStyle(tone.color)
        .padding(.horizontal,9).padding(.vertical,4)
        .background(tone.color.opacity(0.12),in:Capsule())
        .accessibilityElement(children:.ignore)
        .accessibilityLabel(content.badgeAccessibilityLabel)
        .accessibilityIdentifier("permissionBadge-\(content.card.kind.rawValue)")
    }
}

struct PermissionActionButton:View {
    let action:PermissionCardAction
    let send:(PermissionFlowEvent)->Void
    var body:some View {
        let run={ send(.actionTapped(action.action,action.kind)) }
        if action.isPrimary {
            Button(action:run) { Text(action.label) }.buttonStyle(.borderedProminent).tint(MeetingStyle.accent)
                .accessibilityIdentifier("permissionAction-\(action.id)")
        } else {
            Button(action:run) { Text(action.label) }.buttonStyle(.bordered)
                .accessibilityIdentifier("permissionAction-\(action.id)")
        }
    }
}

/// The full card of the onboarding: why, privacy, badge, buttons, the System Settings instruction and recovery notes.
struct PermissionCardView:View {
    let content:PermissionCardContent
    let send:(PermissionFlowEvent)->Void
    private var icon:String {
        switch content.card.kind { case .microphone: return "mic.fill"; case .systemAudio: return "speaker.wave.2.fill"; case .accessibility: return "accessibility" }
    }
    var body:some View {
        let card=content.card
        VStack(alignment:.leading,spacing:12) {
            HStack(alignment:.top,spacing:12) {
                Image(systemName:icon).font(.system(size:17,weight:.medium)).foregroundStyle(MeetingStyle.accent)
                    .frame(width:36,height:36).background(MeetingStyle.accent.opacity(0.10),in:RoundedRectangle(cornerRadius:10)).accessibilityHidden(true)
                VStack(alignment:.leading,spacing:3) {
                    Text(card.title).font(.headline)
                    Text(card.needLabel).font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength:8)
                PermissionBadge(content:content)
            }
            Text(card.reason).font(.callout).fixedSize(horizontal:false,vertical:true)
            Label(content.privacyNote,systemImage:"lock.shield").font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
            if let guide=content.settingsGuide {
                Label(guide,systemImage:"arrow.up.forward.app").font(.callout).fixedSize(horizontal:false,vertical:true)
                    .padding(10).frame(maxWidth:.infinity,alignment:.leading)
                    .background(PermissionTone.waiting.color.opacity(0.10),in:RoundedRectangle(cornerRadius:10))
                    .accessibilityIdentifier("permissionGuide-\(card.kind.rawValue)")
            }
            if !card.footnote.isEmpty { Text(card.footnote).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true) }
            if let relaunch=content.relaunchExplanation { Text(relaunch).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true) }
            if !content.actions.isEmpty {
                HStack(spacing:8) { ForEach(content.actions) { PermissionActionButton(action:$0,send:send) } }
            } else if card.tone != .success {
                Text(PermissionPresentation.restrictedNote).font(.caption.weight(.medium)).foregroundStyle(.secondary)
            }
        }
        .padding(16).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
        .overlay(RoundedRectangle(cornerRadius:16).strokeBorder(card.isFocused ? MeetingStyle.accent.opacity(0.55) : .clear,lineWidth:1.5))
        .accessibilityElement(children:.contain)
        .accessibilityIdentifier("permissionCard-\(card.kind.rawValue)")
    }
}

/// One compact row for Ayarlar → Sistem: icon, title, badge, and the same real buttons.
struct PermissionRowView:View {
    let content:PermissionCardContent
    let send:(PermissionFlowEvent)->Void
    var body:some View {
        let card=content.card
        VStack(alignment:.leading,spacing:6) {
            HStack(spacing:10) {
                VStack(alignment:.leading,spacing:2) {
                    Text(card.title).font(.body.weight(.medium))
                    Text(card.needLabel).font(.caption).foregroundStyle(.secondary)
                }
                Spacer(minLength:8)
                PermissionBadge(content:content)
                ForEach(content.actions) { PermissionActionButton(action:$0,send:send).controlSize(.small) }
            }
            if let guide=content.settingsGuide { Text(guide).font(.caption).foregroundStyle(.secondary) }
            if !card.footnote.isEmpty { Text(card.footnote).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true) }
        }
        .padding(.vertical,6)
        .accessibilityElement(children:.contain)
        .accessibilityIdentifier("permissionRow-\(card.kind.rawValue)")
    }
}
