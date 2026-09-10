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
        out.append(SetupCheck(id:"screen",title:"Ekran kaydı (toplantı sesi)",state:screen ? .ok : .missing,hint:screen ? "izin verildi · yalnız karşı tarafın sesi için (macOS sistem sesini bu izne bağlar); ekran görüntüsü alınmaz, saklanmaz" : "Karşı tarafın sesi (Zoom’dan hoparlöre giden ses) macOS’ta yalnız bu izinle alınabilir; ekran görüntüsü alınmaz, saklanmaz · Sistem Ayarları → Gizlilik ve Güvenlik → Ekran Kaydı"))
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
    /// Shared diagnostics folder: the other Mac's reports are how problems reach the development Mac.
    static func reportsCheck(_ r:[String:Any])->SetupCheck {
        let on=r["reports_on"] as? Bool ?? false, writable=r["reports_writable"] as? Bool ?? false, written=r["reports_written"] as? Int ?? 0
        if !on { return SetupCheck(id:"reports",title:"Teşhis raporları",state:.optional,hint:"Kapalı · açılırsa her toplantıdan sonra iCloud Drive’a özet yazılır") }
        if !writable { return SetupCheck(id:"reports",title:"Teşhis raporları",state:.missing,hint:"iCloud Drive klasörü yok ya da yazılamıyor: \(r["reports_dir"] as? String ?? "")") }
        return SetupCheck(id:"reports",title:"Teşhis raporları",state:.ok,hint:written==0 ? "Açık · henüz rapor yazılmadı (ilk tamamlanan toplantıdan sonra)" : "Açık · \(written) rapor iCloud Drive’da")
    }
    /// The one-line fix for a Mac that has never granted the codesign Keychain partition: without it every
    /// update stops on an unanswerable password prompt, in a Terminal nobody is watching.
    static func signingFix(repo:String)->String {
        let script=(repo.isEmpty || repo=="/tmp") ? "scripts/fix-signing-prompts.sh" : repo+"/scripts/fix-signing-prompts.sh"
        return "Güncelleme başlamadan durur · Terminal’de bir kez: sh "+script
    }
    /// Bridge answer → checks for the pieces the Python side owns. `repo` names the checkout in the signing fix
    /// (empty → the relative path); `divergedNotice` is `UpdateInfo.divergedNotice`, passed in so the setup card
    /// and the sidebar never disagree about a branch that cannot be updated.
    static func serviceChecks(_ r:[String:Any],repo:String="",divergedNotice:String="")->[SetupCheck] {
        let key=r["api_key"] as? Bool ?? false
        let keychain=r["api_key_keychain"] as? Bool ?? false
        let glossary=r["glossary_terms"] as? Int ?? 0
        let shared=r["glossary_shared"] as? Bool ?? false
        let behind=r["update_behind"] as? Int ?? 0
        // The check itself failed (no network, no git): unknown, not up to date. Optional, because a Mac that
        // cannot reach GitHub is not broken — it just cannot answer this question right now.
        let updateError=r["update_error"] as? String ?? ""
        let signing=r["signing_partition"] as? Bool ?? false
        // Either side may notice the divergence first: the bridge's own flag, or the update check the sidebar ran.
        let diverged=(r["update_diverged"] as? Bool ?? false) || !divergedNotice.isEmpty
        let divergedLine=divergedNotice.isEmpty ? UpdateInfo.divergedText(ahead:r["update_ahead"] as? Int ?? 0,hint:r["update_hint"] as? String ?? "") : divergedNotice
        // A key that lives only in the Keychain is not missing: the app copies it into the file the first time it reads it.
        let keyState:SetupCheck.State = key ? .ok : (keychain ? .optional : .missing)
        let keyHint = key ? "anahtar dosyasında kayıtlı (openrouter.key)" : (keychain ? "Anahtar Keychain’de; uygulama bir kez okuyunca dosyaya alınır" : "OpenRouter ile yazıya çevirmede istenir; Ayarlar → Sistem → OpenRouter anahtarı")
        return [
            SetupCheck(id:"key",title:"OpenRouter anahtarı",state:keyState,hint:keyHint),
            SetupCheck(id:"glossary",title:"Proje sözlüğü",state:glossary>0 ? .ok : .optional,hint:glossary>0 ? "\(glossary) terim · \(shared ? "iCloud Drive ile paylaşılıyor" : "yalnız bu Mac")" : "glossary.jsonl içe aktarın; iCloud Drive ile bütün Mac’lere yayılır"),
            SetupCheck(id:"signing",title:"İmzalama izni",state:signing ? .ok : .missing,hint:signing ? "verildi" : signingFix(repo:repo)),
            SetupCheck(id:"update",title:"Sürüm",
                       state:diverged ? .missing : (!updateError.isEmpty ? .optional : (behind==0 ? .ok : .missing)),
                       hint:diverged ? divergedLine : (!updateError.isEmpty ? "kontrol edilemedi · "+updateError : (behind==0 ? "güncel" : "\(behind) değişiklik geride · kenar çubuğundan güncelleyin"))),
            reportsCheck(r),
        ]
    }
}
