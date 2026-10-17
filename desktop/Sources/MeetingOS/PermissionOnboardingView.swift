import SwiftUI

/// Progress bar of the four stops. Each stop is symbol + label, never colour alone.
struct PermissionProgressView:View {
    let state:PermissionFlowState
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            HStack(spacing:0) {
                ForEach(Array(PermissionPresentation.marks(state).enumerated()),id:\.offset) { i,item in
                    if i>0 { Rectangle().fill(.primary.opacity(0.12)).frame(height:1).frame(maxWidth:.infinity).padding(.horizontal,6) }
                    VStack(spacing:4) {
                        Image(systemName:item.mark.symbol).font(.system(size:16))
                            .foregroundStyle(item.mark == .granted ? MeetingStyle.accent : (item.mark == .current ? Color.primary : Color.secondary))
                        Text(item.step.title).font(.caption2).foregroundStyle(item.mark == .current ? .primary : .secondary).lineLimit(1)
                    }
                    .accessibilityElement(children:.ignore)
                    .accessibilityLabel("\(item.step.title): \(item.mark.spoken)")
                }
            }
            Text(PermissionPresentation.progressText(state)).font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityIdentifier("permissionProgress")
    }
}

/// The permission onboarding: one grant at a time, then "Tamam". Consumes `PermissionFlowState` and reports
/// every tap as a `PermissionFlowEvent`; the driver behind `send` owns the provider, so nothing here touches the system.
struct PermissionOnboardingView:View {
    let state:PermissionFlowState
    let send:(PermissionFlowEvent)->Void

    var body:some View {
        let step=PermissionPresentation.currentStep(state)
        VStack(alignment:.leading,spacing:18) {
            VStack(alignment:.leading,spacing:6) {
                Text("Meeting OS’u kayda hazırlayalım").font(.title2.bold())
                Text("Toplantıyı kaydedebilmek için macOS’un birkaç izni gerekiyor. Her birini neden istediğimizi altında yazdık; hiçbiri sizi bir şey yapmaya zorlamadan değişmez.")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
            }
            PermissionProgressView(state:state)
            if let kind=step.kind {
                PermissionCardView(content:PermissionPresentation.content(kind,state),send:send)
            } else {
                PermissionDoneView(state:state,send:send)
            }
        }
        .padding(24).frame(maxWidth:520,alignment:.leading)
        .accessibilityIdentifier("permissionOnboarding")
    }
}

/// "Tamam": what is on, what is still off and how to get back.
struct PermissionDoneView:View {
    let state:PermissionFlowState
    let send:(PermissionFlowEvent)->Void
    var body:some View {
        let ready=state.snapshot.missingRequired.isEmpty
        let missing=PermissionPresentation.missingOptional(state)
        VStack(alignment:.leading,spacing:12) {
            Label(PermissionPresentation.doneTitle(state),systemImage:ready ? "checkmark.seal.fill" : "exclamationmark.triangle.fill")
                .font(.headline).foregroundStyle(ready ? MeetingStyle.accent : .orange)
            Text(PermissionPresentation.doneDetail(state)).font(.callout).fixedSize(horizontal:false,vertical:true)
            if !missing.isEmpty {
                VStack(alignment:.leading,spacing:6) {
                    Text("Açılmayan isteğe bağlı izinler").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                    ForEach(missing,id:\.self) { Label(PermissionPresentation.optionalLine($0,state),systemImage:"minus.circle").font(.callout) }
                    Text(PermissionPresentation.reopenHint).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                }
            }
            Button { send(.finish) } label: { Text(PermissionPresentation.finishLabel) }
                .buttonStyle(.borderedProminent).tint(MeetingStyle.accent).keyboardShortcut(.defaultAction)
                .accessibilityIdentifier("permissionFinish")
        }
        .padding(16).frame(maxWidth:.infinity,alignment:.leading).meetingCard()
        .accessibilityIdentifier("permissionDone")
    }
}

/// Ayarlar → Sistem: the three grants as compact rows plus the way back into the onboarding.
struct PermissionSettingsSection:View {
    let state:PermissionFlowState
    let send:(PermissionFlowEvent)->Void
    var body:some View {
        VStack(alignment:.leading,spacing:8) {
            Text("İzinler").font(.headline)
            VStack(spacing:0) {
                ForEach(Array(PermissionPresentation.contents(state).enumerated()),id:\.element.card.kind) { i,c in
                    if i>0 { Divider() }
                    PermissionRowView(content:c,send:send)
                }
            }
            Button { send(.reopen) } label: { Label(PermissionPresentation.reopenSetupLabel,systemImage:"arrow.counterclockwise") }
                .accessibilityIdentifier("permissionReopen")
        }
        .accessibilityIdentifier("permissionSettingsSection")
    }
}
