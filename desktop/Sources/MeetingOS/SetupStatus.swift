import AppKit
import AVFoundation
import EventKit
import Foundation
import UserNotifications

/// One glance at what this Mac still needs: the permissions a recording depends on, the API key, the shared glossary.
/// Built for the second Mac, where a missing permission looked like a broken app.
struct SetupCheck: Identifiable, Equatable {
    enum State: Equatable { case ok, missing, optional, unknown }
    let id:String; let title:String; let state:State; let hint:String
}

enum SetupStatus {
    /// What the "Düzelt" button on a check does: ask macOS, or open the exact System Settings pane when only the user can change it.
    static let panes=["mic":"Privacy_Microphone","screen":"Privacy_ScreenCapture","calendar":"Privacy_Calendars","reminders":"Privacy_Reminders"]
    /// macOS asks only once. Undetermined → ask now; already refused → open the exact System Settings pane, the only place it can change.
    static func fix(_ id:String,calendarWanted:Bool,done:@escaping ()->Void) {
        let finish={ DispatchQueue.main.async(execute:done) }
        switch id {
        case "mic":
            if AVCaptureDevice.authorizationStatus(for:.audio) == .notDetermined { AVCaptureDevice.requestAccess(for:.audio) { _ in finish() } }
            else { openPane("Privacy_Microphone"); finish() }
        case "screen":
            if !CGRequestScreenCaptureAccess() { openPane("Privacy_ScreenCapture") }
            DispatchQueue.main.asyncAfter(deadline:.now()+1,execute:done)
        case "calendar":
            if EKEventStore.authorizationStatus(for:.event) == .notDetermined { CalendarContext.requestAccess { _ in done() } }
            else { openPane("Privacy_Calendars"); finish() }
        case "reminders":
            if EKEventStore.authorizationStatus(for:.reminder) == .notDetermined { RemindersBridge.requestAccess { _ in done() } }
            else { openPane("Privacy_Reminders"); finish() }
        case "notify":
            UNUserNotificationCenter.current().getNotificationSettings { s in
                if s.authorizationStatus == .notDetermined { UNUserNotificationCenter.current().requestAuthorization(options:[.alert,.sound]) { _,_ in finish() } }
                else { open("x-apple.systempreferences:com.apple.Notifications-Settings.extension"); finish() }
            }
        default: done()
        }
    }
    static func openPane(_ pane:String) { open("x-apple.systempreferences:com.apple.preference.security?\(pane)") }
    /// Button label: a prompt is still possible only while macOS has never been asked.
    static func fixLabel(_ c:SetupCheck)->String { c.state == .unknown ? "İzin iste" : "Ayarları aç" }
    static func open(_ url:String) { DispatchQueue.main.async { if let u=URL(string:url) { NSWorkspace.shared.open(u) } } }   // callbacks arrive off the main thread
    static func fixable(_ c:SetupCheck)->Bool { ["mic","screen","calendar","reminders","notify"].contains(c.id) && c.state != .ok }
    static func permissionChecks(calendarWanted:Bool)->[SetupCheck] {
        var out:[SetupCheck]=[]
        let mic=AVCaptureDevice.authorizationStatus(for:.audio)
        out.append(SetupCheck(id:"mic",title:"Mikrofon",state:mic == .authorized ? .ok : (mic == .notDetermined ? .unknown : .missing),hint:mic == .authorized ? "izin verildi" : "Sistem Ayarları → Gizlilik ve Güvenlik → Mikrofon"))
        let screen=CGPreflightScreenCaptureAccess()
        out.append(SetupCheck(id:"screen",title:"Ekran kaydı (toplantı sesi)",state:screen ? .ok : .missing,hint:screen ? "izin verildi" : "Sistem Ayarları → Gizlilik ve Güvenlik → Ekran Kaydı; sistem sesi bu izinle alınır"))
        let cal=EKEventStore.authorizationStatus(for:.event)
        let calOK:Bool = { if #available(macOS 14,*) { return cal == .fullAccess }; return cal == .authorized }()
        out.append(SetupCheck(id:"calendar",title:"Takvim (isteğe bağlı)",state:calOK ? .ok : (calendarWanted ? .missing : .optional),hint:calOK ? "izin verildi" : (calendarWanted ? "Ayar açık ama izin yok: Sistem Ayarları → Takvimler" : "Ayarlarda açılırsa istenir")))
        let rem=EKEventStore.authorizationStatus(for:.reminder)
        let remOK:Bool = { if #available(macOS 14,*) { return rem == .fullAccess }; return rem == .authorized }()
        out.append(SetupCheck(id:"reminders",title:"Hatırlatıcılar (isteğe bağlı)",state:remOK ? .ok : .optional,hint:remOK ? "izin verildi" : "İlk “Hatırlatıcılar’a ekle” tıklamasında istenir"))
        return out
    }
    static func notificationCheck(_ settings:UNNotificationSettings)->SetupCheck {
        let ok=settings.authorizationStatus == .authorized || settings.authorizationStatus == .provisional
        return SetupCheck(id:"notify",title:"Bildirimler",state:ok ? .ok : (settings.authorizationStatus == .notDetermined ? .unknown : .optional),hint:ok ? "izin verildi" : "Transkript bitince ve Zoom açılınca bildirim için Sistem Ayarları → Bildirimler")
    }
    /// Bridge answer → checks for the pieces the Python side owns.
    static func serviceChecks(_ r:[String:Any])->[SetupCheck] {
        let key=r["api_key"] as? Bool ?? false
        let glossary=r["glossary_terms"] as? Int ?? 0
        let shared=r["glossary_shared"] as? Bool ?? false
        let behind=r["update_behind"] as? Int ?? 0
        return [
            SetupCheck(id:"key",title:"OpenRouter anahtarı",state:key ? .ok : .missing,hint:key ? "Keychain’de kayıtlı" : "OpenRouter ile yazıya çevirmede istenir; Keychain’e bir kez kaydedilir"),
            SetupCheck(id:"glossary",title:"Proje sözlüğü",state:glossary>0 ? .ok : .optional,hint:glossary>0 ? "\(glossary) terim · \(shared ? "iCloud Drive ile paylaşılıyor" : "yalnız bu Mac")" : "glossary.jsonl içe aktarın; iCloud Drive ile bütün Mac’lere yayılır"),
            SetupCheck(id:"update",title:"Sürüm",state:behind==0 ? .ok : .missing,hint:behind==0 ? "güncel" : "\(behind) değişiklik geride · kenar çubuğundan güncelleyin"),
        ]
    }
}
