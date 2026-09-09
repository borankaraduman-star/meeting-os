import SwiftUI
import AppKit

/// Small always-on-top panel shown while recording: elapsed time, mark buttons and stop. It floats above
/// Zoom without taking focus, so the user never has to find the main window mid-meeting.
enum RecorderPanel {
    private static var panel:NSPanel?
    static func show(model:Model) {
        if panel != nil { return }
        let view=NSHostingView(rootView:RecorderPanelView(model:model))
        view.frame=NSRect(x:0,y:0,width:300,height:56)
        let p=NSPanel(contentRect:view.frame,styleMask:[.nonactivatingPanel,.titled,.fullSizeContentView,.utilityWindow],backing:.buffered,defer:false)
        p.titleVisibility = .hidden; p.titlebarAppearsTransparent=true; p.isMovableByWindowBackground=true
        p.level = .floating; p.collectionBehavior=[.canJoinAllSpaces,.fullScreenAuxiliary,.stationary]
        p.contentView=view; p.isReleasedWhenClosed=false; p.hidesOnDeactivate=false
        if let screen=NSScreen.main { let f=screen.visibleFrame; p.setFrameOrigin(NSPoint(x:f.maxX-view.frame.width-16,y:f.maxY-view.frame.height-16)) }
        p.orderFrontRegardless(); panel=p
    }
    static func hide() { panel?.orderOut(nil); panel=nil }
}

struct RecorderPanelView:View {
    @ObservedObject var model:Model
    var body:some View {
        HStack(spacing:10) {
            Circle().fill(.red).frame(width:10,height:10)
            Text(model.elapsedText).font(.system(.body,design:.monospaced).weight(.semibold)).monospacedDigit()
            Text("Meeting OS").font(.caption).foregroundStyle(.secondary)
            Spacer()
            Button("An") { model.markMoment("important") }.help("Önemli an (⌃⌥M)")
            Button("Karar") { model.markMoment("decision") }.help("Karar anı (⌘⇧M)")
            Button("Bitir") { model.stop() }.buttonStyle(.borderedProminent).tint(.red).help("Kaydı bitir (⌃⌥R)")
        }.controlSize(.small).padding(.horizontal,12).padding(.vertical,8).frame(width:300,height:56)
    }
}
