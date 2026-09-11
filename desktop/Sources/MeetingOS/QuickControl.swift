import SwiftUI
import AppKit
import Carbon.HIToolbox

/// Zoom detection from the window list: cheap enough for the two-second refresh, no permissions needed.
enum ZoomWatch {
    static let bundle="us.zoom.xos"
    /// Window names Zoom uses while the local user is presenting: the green "you are screen sharing" strip and
    /// the floating share toolbar it leaves behind when the meeting window is minimised. Matched case- and
    /// locale-insensitively, in English and Turkish. The bare word "share" is deliberately not on this list —
    /// it also matches the share *picker*, and `classify` already counts that as a meeting window.
    static let sharingNames=["screen sharing","screen share","sharing screen","share toolbar","share statusbar","sharing toolbar","ekran paylaş","paylaşım araç"]
    /// One window's verdict: a real meeting window (or the share toolbar Zoom leaves when the meeting window is
    /// minimised for screen sharing), only the "Zoom Workplace" home window, or evidence that the local user is
    /// presenting right now. A sharing window is always a meeting window too.
    static func classify(_ w:[String:Any])->(meeting:Bool,home:Bool,sharing:Bool) {
        guard (w["kCGWindowOwnerName"] as? String ?? "").lowercased().contains("zoom") else { return (false,false,false) }
        let name=(w["kCGWindowName"] as? String ?? "")
        if sharingNames.contains(where:{ name.localizedCaseInsensitiveContains($0) }) { return (true,false,true) }
        if name.localizedCaseInsensitiveContains("Zoom Meeting") || name.localizedCaseInsensitiveContains("Toplantı") || name.localizedCaseInsensitiveContains("share") || name.localizedCaseInsensitiveContains("Paylaş") { return (true,false,false) }
        return (false,(w["kCGWindowLayer"] as? Int ?? 0)==0 && name.localizedCaseInsensitiveContains("Zoom Workplace"),false)
    }
    /// `strict` ignores the "Zoom Workplace" home window: hands-free recording must only follow a real meeting window.
    static func meetingOpen(windows:[[String:Any]],runningBundles:Set<String>,strict:Bool=false)->Bool {
        guard runningBundles.contains(bundle) else { return false }
        return windows.contains { let c=classify($0); return c.meeting || (!strict && c.home) }
    }
    /// All three flags from one walk of the window list: it can hold hundreds of entries, so it is walked once.
    /// `sharing` cannot short-circuit on the first meeting window the way this used to — the share strip may sit
    /// anywhere in the list — so the loop stops only once both verdicts are settled.
    static func flags(windows:[[String:Any]],runningBundles:Set<String>)->(open:Bool,strict:Bool,sharing:Bool) {
        guard runningBundles.contains(bundle) else { return (false,false,false) }
        var home=false, meeting=false, sharing=false
        for w in windows {
            let c=classify(w)
            if c.meeting { meeting=true }
            if c.home { home=true }
            if c.sharing { sharing=true }
            if meeting && sharing { break }
        }
        return (meeting || home,meeting,sharing)
    }
    static func current(strict:Bool=false)->Bool { let st=state(); return st.strict || (!strict && st.open) }
    /// The same reading, with the expensive half off the main actor. The window list can hold hundreds of
    /// entries and was walked on the main thread every two seconds for the whole of a Zoom recording — the one
    /// stretch where the main thread also owns the transcript's layout. Only the running-app list stays here;
    /// the walk hops to a utility queue and comes back as two Bools, so stop detection keeps its cadence.
    @MainActor static func stateAsync() async -> (open:Bool,strict:Bool,sharing:Bool,running:Bool) {
        let running=Set(NSWorkspace.shared.runningApplications.compactMap(\.bundleIdentifier))
        guard running.contains(bundle) else { return (false,false,false,false) }
        let f:(open:Bool,strict:Bool,sharing:Bool) = await withCheckedContinuation { cont in
            DispatchQueue.global(qos:.utility).async {
                let list=(CGWindowListCopyWindowInfo([.optionAll,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]]) ?? []   // all Spaces: a full-screen Keynote must not hide the meeting
                cont.resume(returning:flags(windows:list,runningBundles:running))
            }
        }
        return (f.open,f.strict,f.sharing,true)
    }
    /// Scan cadence. Every sixth second is enough for the menu bar and the Zoom reminder; hands-free recording is
    /// the one caller that must see a meeting window open or close quickly, and only while Zoom is running.
    static func shouldScan(tick:Int,autoRecord:Bool,zoomRunning:Bool)->Bool { (autoRecord && zoomRunning) || tick%3==0 }
    /// One window-list read per scan: `open` for reminders and the menu bar, `strict` for hands-free recording,
    /// `sharing` for discreet mode.
    static func state()->(open:Bool,strict:Bool,sharing:Bool,running:Bool) {
        let running=Set(NSWorkspace.shared.runningApplications.compactMap(\.bundleIdentifier))
        guard running.contains(bundle) else { return (false,false,false,false) }
        let list=(CGWindowListCopyWindowInfo([.optionAll,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]]) ?? []   // all Spaces: a full-screen Keynote must not hide the meeting
        let f=flags(windows:list,runningBundles:running)
        return (f.open,f.strict,f.sharing,true)
    }
}

/// System-wide shortcuts through Carbon hot keys: work while Zoom is frontmost, need no Accessibility grant.
/// ⌃⌥R starts/ends the recording, ⌃⌥M marks a moment, ⌃⌥V records my own voice too.
enum GlobalHotkeys {
    static let record:UInt32=1, mark:UInt32=2, mic:UInt32=3
    private static var refs:[EventHotKeyRef?]=[]
    private static var installed=false
    static func keyName(_ id:UInt32)->String { id==record ? "⌃⌥R" : (id==mic ? "⌃⌥V" : "⌃⌥M") }
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
        for (id,code) in [(record,UInt32(kVK_ANSI_R)),(mark,UInt32(kVK_ANSI_M)),(mic,UInt32(kVK_ANSI_V))] {
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
    @ObservedObject var recorder:RecorderState
    @ObservedObject var jobs:JobState
    init(model:Model) { self.model=model; _recorder=ObservedObject(wrappedValue:model.recorder); _jobs=ObservedObject(wrappedValue:model.jobs) }
    var body:some View {
        Text(model.recording ? "Kayıt sürüyor · \(recorder.elapsedText)" : (model.busy ? "İşlem sürüyor · \(jobs.jobProgress.isEmpty ? "lütfen bekleyin" : jobs.jobProgress)" : "Hazır"))
        if model.zoomMeetingOpen && !model.recording { Text("Zoom toplantısı açık").foregroundStyle(.secondary) }
        if !model.recording, model.useCalendar, let cal=CalendarContext.currentCached() { Text("Takvim: \(cal.title)").foregroundStyle(.secondary) }
        Divider()
        Button(model.recording ? "Kaydı bitir  ⌃⌥R" : "Yeni kayıt  ⌃⌥R") { if model.recording { model.stop() } else { model.beginRecording() } }.disabled(!model.recording && model.recordProcess != nil)
        if model.recording {
            Text(model.micStatusLine).foregroundStyle(.secondary)
            Button(MicGate.overrideLabel(model.micManualOn)) { model.toggleMicManual() }
            micModeMenu
            Button("An  ⌃⌥M") { model.markMoment("important") }
            Button("Karar") { model.markMoment("decision") }
            Button("Görev") { model.markMoment("task") }
            Button("Sonra") { model.markMoment("later") }
        }
        if !model.recording { micModeMenu }
        if let u=model.update, u.canUpdate { Divider(); Button((model.zoomMeetingOpen ? "Güncelleme toplantı bitince" : "Güncelle ve yeniden başlat")+" · \(u.behind) değişiklik") { model.startUpdate() }.disabled(model.busy || model.recording || model.updating || model.zoomMeetingOpen) }
        Divider()
        Button("Uygulamayı göster") { model.showMainWindow() }
        if !model.recording, let last=model.meetings.first { Button("Son toplantıyı aç · \(String(last.title.prefix(28)))") { model.selected=last.id; model.tab="analysis"; model.showMainWindow() } }
        if !model.recording, model.meeting != nil { Button("Kontrol sekmesini aç") { model.tab="review"; model.showMainWindow() } }
        Button("Meeting OS’i kapat") { NSApp.terminate(nil) }
    }
    /// The same three-way choice as Ayarlar → Genel, one click from the menu bar: the mic gate is the setting
    /// somebody wants to change *because of* the meeting they are in, not before it.
    @ViewBuilder var micModeMenu:some View {
        Menu("Mikrofonum · "+MicGate.label(model.micMode)) {
            Picker("Mikrofonum",selection:$model.micMode) { ForEach(MicGate.modes,id:\.self) { Text(MicGate.label($0)).tag($0) } }.pickerStyle(.inline).labelsHidden()
        }
    }
}


import CoreAudio
/// Is the default input device in use by any process (Zoom, Meet, Teams…)? Needs no permission; used so a
/// hands-free recording is never ended while somebody is still on a call.
enum AudioInUse {
    static func microphoneBusy()->Bool {
        var device=AudioDeviceID(0); var size=UInt32(MemoryLayout<AudioDeviceID>.size)
        var addr=AudioObjectPropertyAddress(mSelector:kAudioHardwarePropertyDefaultInputDevice,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject),&addr,0,nil,&size,&device)==noErr, device != 0 else { return false }
        var running=UInt32(0); size=UInt32(MemoryLayout<UInt32>.size)
        addr=AudioObjectPropertyAddress(mSelector:kAudioDevicePropertyDeviceIsRunningSomewhere,mScope:kAudioObjectPropertyScopeGlobal,mElement:kAudioObjectPropertyElementMain)
        guard AudioObjectGetPropertyData(device,&addr,0,nil,&size,&running)==noErr else { return false }
        return running != 0
    }
}
