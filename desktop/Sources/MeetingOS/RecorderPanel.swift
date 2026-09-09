import SwiftUI
import AppKit

/// Small always-on-top panel shown while recording: elapsed time, mark buttons and stop. It floats above
/// Zoom without taking focus, so the user never has to find the main window mid-meeting.
enum RecorderPanel {
    private static var panel:NSPanel?
    static func show(model:Model) {
        if panel != nil { return }
        let view=NSHostingView(rootView:RecorderPanelView(model:model))
        view.frame=NSRect(x:0,y:0,width:400,height:56)
        let p=NSPanel(contentRect:view.frame,styleMask:[.nonactivatingPanel,.titled,.fullSizeContentView,.utilityWindow],backing:.buffered,defer:false)
        p.titleVisibility = .hidden; p.titlebarAppearsTransparent=true; p.isMovableByWindowBackground=true
        p.level = .floating; p.collectionBehavior=[.canJoinAllSpaces,.fullScreenAuxiliary,.stationary]
        p.sharingType = .none   // excluded from screen sharing and screenshots: nobody in the meeting sees the recorder
        p.contentView=view; p.isReleasedWhenClosed=false; p.hidesOnDeactivate=false
        if let screen=NSScreen.main { let f=screen.visibleFrame; p.setFrameOrigin(NSPoint(x:f.maxX-view.frame.width-16,y:f.maxY-view.frame.height-16)) }
        p.orderFrontRegardless(); panel=p
    }
    static func hide() { panel?.orderOut(nil); panel=nil }
}

struct RecorderPanelView:View {
    @ObservedObject var model:Model
    @ObservedObject var recorder:RecorderState
    init(model:Model) { self.model=model; _recorder=ObservedObject(wrappedValue:model.recorder) }
    var body:some View {
        HStack(spacing:10) {
            Circle().fill(.red).frame(width:10,height:10)
            Text(recorder.elapsedText).font(.system(.body,design:.monospaced).weight(.semibold)).monospacedDigit()
            // The meeting is in progress: a line about a survived interruption replaces the title in place —
            // no notification, no sound, nothing that moves or asks for attention.
            Text(recorder.recordingNotice.isEmpty ? (model.recordingTitle.isEmpty ? "Meeting OS" : model.recordingTitle) : recorder.recordingNotice)
                .font(.caption).foregroundStyle(recorder.recordingNotice.isEmpty ? AnyShapeStyle(.secondary) : AnyShapeStyle(.orange))
                .lineLimit(1).truncationMode(.tail).frame(maxWidth:110,alignment:.leading)
                .help(recorder.recordingNotice.isEmpty ? model.recordingTitle : recorder.recordingNotice)
            SignalDot(label:"Mik",state:recorder.captureDots["mic"] ?? "unknown")
            SignalDot(label:"Sis",state:recorder.captureDots["system"] ?? "unknown")
            if model.markerCount>0 { Text("⌘M \(model.markerCount)").font(.caption2.monospacedDigit()).foregroundStyle(.secondary).help("İşaretlenen an sayısı") }
            Spacer()
            Button("An") { model.markMoment("important") }.help("An (⌃⌥M)")
            Button("Karar") { model.markMoment("decision") }.help("Karar (⌘⇧M)")
            Button("Bitir") { model.stop() }.buttonStyle(.borderedProminent).tint(.red).help("Kaydı bitir (⌃⌥R)")
        }.controlSize(.small).padding(.horizontal,12).padding(.vertical,8).frame(width:400,height:56).preferredColorScheme(model.colorScheme)
    }
}


/// One capture source at a glance: green = signal, grey = silent, orange = stale reading, hollow = not checked yet.
struct SignalDot:View {
    let label:String; let state:String
    static func color(_ state:String)->Color { switch state { case "ok": return .green; case "silent": return .secondary; case "stale": return .orange; default: return .clear } }
    static func hint(_ state:String)->String { switch state { case "ok": return "Sinyal var"; case "silent": return "Sessiz · ses gelmiyor"; case "stale": return "Son okuma eski"; default: return "Henüz doğrulanmadı" } }
    var body:some View {
        HStack(spacing:3) {
            Circle().fill(Self.color(state)).overlay(Circle().stroke(Color.secondary.opacity(0.6),lineWidth:state=="unknown" ? 1 : 0)).frame(width:7,height:7)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }.help("\(label=="Mik" ? "Mikrofon" : "Sistem sesi"): \(Self.hint(state))").accessibilityLabel("\(label) \(Self.hint(state))")
    }
}
