import SwiftUI
import AppKit
import Carbon.HIToolbox

/// Zoom detection from the window list: cheap enough for the two-second refresh, no permissions needed.
enum ZoomWatch {
    static let bundle="us.zoom.xos"
    /// `strict` ignores the "Zoom Workplace" home window: hands-free recording must only follow a real meeting window.
    static func meetingOpen(windows:[[String:Any]],runningBundles:Set<String>,strict:Bool=false)->Bool {
        guard runningBundles.contains(bundle) else { return false }
        return windows.contains { w in
            let owner=(w["kCGWindowOwnerName"] as? String ?? "").lowercased()
            let name=(w["kCGWindowName"] as? String ?? "")
            let layer=w["kCGWindowLayer"] as? Int ?? 0
            let meeting=name.localizedCaseInsensitiveContains("Zoom Meeting") || name.localizedCaseInsensitiveContains("Toplantı")
            return owner.contains("zoom") && layer==0 && (meeting || (!strict && name.localizedCaseInsensitiveContains("Zoom Workplace")))
        }
    }
    static func current(strict:Bool=false)->Bool { state().strict || (!strict && state().open) }
    /// One window-list read per poll: `open` for reminders and the menu bar, `strict` for hands-free recording.
    static func state()->(open:Bool,strict:Bool) {
        let running=Set(NSWorkspace.shared.runningApplications.compactMap(\.bundleIdentifier))
        guard running.contains(bundle) else { return (false,false) }
        let list=(CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]]) ?? []
        return (meetingOpen(windows:list,runningBundles:running),meetingOpen(windows:list,runningBundles:running,strict:true))
    }
}

/// System-wide shortcuts through Carbon hot keys: work while Zoom is frontmost, need no Accessibility grant.
/// ⌃⌥R starts/ends the recording, ⌃⌥M marks a moment.
enum GlobalHotkeys {
    static let record:UInt32=1, mark:UInt32=2
    private static var refs:[EventHotKeyRef?]=[]
    private static var installed=false
    static func keyName(_ id:UInt32)->String { id==record ? "⌃⌥R" : "⌃⌥M" }
    static func install(handler:@escaping (UInt32)->Void) {
        guard !installed else { return }   // the window can reappear; one handler, one registration
        installed=true
        var spec=EventTypeSpec(eventClass:OSType(kEventClassKeyboard),eventKind:UInt32(kEventHotKeyPressed))
        let callback:EventHandlerUPP={ _,event,userData in
            var hk=EventHotKeyID()
            GetEventParameter(event,EventParamName(kEventParamDirectObject),EventParamType(typeEventHotKeyID),nil,MemoryLayout<EventHotKeyID>.size,nil,&hk)
            if let userData { Unmanaged<HotkeyBox>.fromOpaque(userData).takeUnretainedValue().handler(hk.id) }
            return noErr
        }
        let box=HotkeyBox(handler:handler)
        InstallEventHandler(GetApplicationEventTarget(),callback,1,&spec,Unmanaged.passRetained(box).toOpaque(),nil)
        let mods=UInt32(controlKey|optionKey)
        for (id,code) in [(record,UInt32(kVK_ANSI_R)),(mark,UInt32(kVK_ANSI_M))] {
            var ref:EventHotKeyRef?
            RegisterEventHotKey(code,mods,EventHotKeyID(signature:OSType(0x4D4F5321),id:id),GetApplicationEventTarget(),0,&ref)
            refs.append(ref)
        }
    }
    final class HotkeyBox { let handler:(UInt32)->Void; init(handler:@escaping (UInt32)->Void) { self.handler=handler } }
}

/// Menu-bar control: visible above every app, one click to start or end, marks while recording.
struct QuickMenu:View {
    @ObservedObject var model:Model
    var body:some View {
        Text(model.recording ? "Kayıt sürüyor · \(model.elapsedText)" : (model.busy ? "İşlem sürüyor · \(model.jobProgress.isEmpty ? "lütfen bekleyin" : model.jobProgress)" : "Hazır"))
        if model.zoomMeetingOpen && !model.recording { Text("Zoom toplantısı açık").foregroundStyle(.secondary) }
        if !model.recording, model.useCalendar, let cal=CalendarContext.currentCached() { Text("Takvim: \(cal.title)").foregroundStyle(.secondary) }
        Divider()
        Button(model.recording ? "Kaydı bitir  ⌃⌥R" : "Yeni kayıt  ⌃⌥R") { model.recording ? model.stop() : model.start() }.disabled(model.busy && !model.recording)
        if model.recording {
            Button("An  ⌃⌥M") { model.markMoment("important") }
            Button("Karar") { model.markMoment("decision") }
            Button("Görev") { model.markMoment("task") }
            Button("Sonra") { model.markMoment("later") }
        }
        if let u=model.update, u.available { Divider(); Button((model.zoomMeetingOpen ? "Güncelleme toplantı bitince" : "Güncelle ve yeniden başlat")+" · \(u.behind) değişiklik") { model.startUpdate() }.disabled(model.busy || model.recording || model.updating || model.zoomMeetingOpen) }
        Divider()
        Button("Uygulamayı göster") { model.showMainWindow() }
        if !model.recording, let last=model.meetings.first { Button("Son toplantıyı aç · \(String(last.title.prefix(28)))") { model.selected=last.id; model.tab="analysis"; model.showMainWindow() } }
        if !model.recording, model.meeting != nil { Button("Kontrol sekmesini aç") { model.tab="review"; model.showMainWindow() } }
        Button("Meeting OS’i kapat") { NSApp.terminate(nil) }
    }
}
