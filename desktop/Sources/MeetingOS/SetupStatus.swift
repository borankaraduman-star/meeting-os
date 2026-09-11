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
    static let panes=["mic":"Privacy_Microphone","screen":"Privacy_ScreenCapture","calendar":"Privacy_Calendars","reminders":"Privacy_Reminders","accessibility":"Privacy_Accessibility"]
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
        case "accessibility":
            // The prompt is the only thing that puts Meeting OS into the Accessibility list; the pane is opened
            // straight after, because the switch still has to be flicked there by hand.
            if !ZoomMute.requestTrust() { openPane("Privacy_Accessibility") }
            DispatchQueue.main.asyncAfter(deadline:.now()+1,execute:done)
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
    static func fixable(_ c:SetupCheck)->Bool { ["mic","screen","calendar","reminders","notify","accessibility"].contains(c.id) && c.state != .ok }
    /// Why the Accessibility grant exists at all: it is the only way to read Zoom's own mute state, and without
    /// it `MicGate` keeps the microphone shut in `zoom` mode. Optional, never missing — a Mac that never grants
    /// it still records perfectly, it just needs ⌃⌥V for the owner's own voice.
    static func accessibilityCheck(trusted:Bool=ZoomMute.trusted(),mode:String=MicGate.mode)->SetupCheck {
        let title="Erişilebilirlik (Zoom’da sesiniz açıkken mikrofonu kaydetmek için)"
        if trusted { return SetupCheck(id:"accessibility",title:title,state:.ok,hint:"izin verildi · Zoom’un mikrofon durumu okunabiliyor") }
        let cost = mode=="zoom" ? "Şu an “Zoom’u izle” modundasınız: izin olmadan kendi sesiniz yalnız ⌃⌥V ile kaydedilir." : "“Zoom’u izle” moduna geçerseniz gerekir."
        return SetupCheck(id:"accessibility",title:title,state:.optional,
                          hint:"Meeting OS, Zoom’un Toplantı menüsünden yalnız “Sesi Aç/Sesi Kapat” satırını okur; tuş vuruşu ya da ekran içeriği okunmaz. "+cost+" · Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik")
    }
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
        out.append(accessibilityCheck())
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
    /// Is the fleet correcting MORE than it was? One line, built by the Python side from the daily numbers
    /// every Mac puts in its heartbeat (`quality.quality_trend`), and nothing at all when there is no answer
    /// yet: a Mac with no shared folder, no heartbeats or no measured day must not get a row saying zero.
    /// `.optional` unless the pooled error rate rose 30 % or more with enough observations behind both
    /// periods — the same bar as the fleet alert, so the card and the alert can never disagree.
    /// The identity calibration rides in the same row (Codex #5): what this Mac's own time-ordered,
    /// human-verified evidence says about the voice-matching threshold. It is a RECOMMENDATION and the row
    /// says so — nothing is applied until the user runs `quality calibrate --apply`. Below the evidence bar
    /// it reads "veri yetersiz (n=…)", which is the honest answer and never a state worth colouring red.
    /// 1.2.85 adds two things to the same row: the calibration line gains "· otomatik uygulama kapalı" while
    /// automatic promotion is off (a recommendation the machine will not act on has to say so where it is
    /// read), and the live policy version rides on the end once one has been promoted.
    static func qualityCheck(_ r:[String:Any])->SetupCheck? {
        let trend=r["quality_trend"] as? [String:Any] ?? [:]
        let line=(trend["line"] as? String ?? "").trimmingCharacters(in:.whitespaces)
        let calibration=(r["calibration"] as? [String:Any])?["line"] as? String ?? ""
        // Which policy version this Mac is running (1.2.85). Absent until something has actually been
        // promoted: a row reading "politika v0" would announce a thing that never happened.
        let policy=(r["policy"] as? [String:Any])?["line"] as? String ?? ""
        let parts=[line,calibration.trimmingCharacters(in:.whitespaces),policy.trimmingCharacters(in:.whitespaces)].filter { !$0.isEmpty }
        if parts.isEmpty { return nil }
        let change=trend["change"] as? Double ?? 0
        let eligible=trend["eligible"] as? Bool ?? false
        let worse=eligible && change >= 0.30
        let worst=(trend["top_errors"] as? [[String:Any]])?.first?["metric"] as? String ?? ""
        let tail=worse && !worst.isEmpty ? " · en çok: "+(errorLabels[worst] ?? worst) : ""
        return SetupCheck(id:"quality",title:"Kalite eğilimi",state:worse ? .missing : .optional,hint:parts.joined(separator:" · ")+tail)
    }
    /// "ekipten gelen profiller: +2 doğru / −1 yanlış" — the counterfactual, appended to whatever the team row
    /// already says. Empty (and therefore absent) until the idle housekeeping has measured a non-zero effect,
    /// so a Mac with no team, or one whose team changed nothing, gets no line at all rather than a zero.
    static func teamEffectTail(_ r:[String:Any])->String {
        let line=((r["team_profile_effect"] as? [String:Any])?["line"] as? String ?? "").trimmingCharacters(in:.whitespaces)
        return line.isEmpty ? "" : " · "+line
    }
    static let errorLabels=["names_falsified":"yanlış otomatik isim","word_repeat_errors":"öğretilen kelime yine yanlış",
                            "summary_edits":"özet düzeltmesi","task_edits":"görev düzeltmesi"]
    /// The one-line fix for a Mac that has never granted the codesign Keychain partition: without it every
    /// update stops on an unanswerable password prompt, in a Terminal nobody is watching.
    static func signingFix(repo:String)->String {
        let script=(repo.isEmpty || repo=="/tmp") ? "scripts/fix-signing-prompts.sh" : repo+"/scripts/fix-signing-prompts.sh"
        return "Güncelleme başlamadan durur · Terminal’de bir kez: sh "+script
    }
    /// Bridge answer → checks for the pieces the Python side owns. `repo` names the checkout in the signing fix
    /// (empty → the relative path); `divergedNotice` is `UpdateInfo.divergedNotice`, passed in so the setup card
    /// and the sidebar never disagree about a branch that cannot be updated.
    /// The shared knowledge base (profiles, words, glossary) needs a folder every teammate can reach. A Mac with no
    /// team folder and no iCloud Drive silently shares nothing — say so here instead.
    static func teamRootCheck(_ r:[String:Any])->SetupCheck {
        let kind=r["team_root_kind"] as? String ?? "none"; let root=r["team_root"] as? String ?? ""
        switch kind {
        case "cloud":
            // Zero setup: the team is whoever installed with the same OpenRouter key, and the mirror the app
            // reads is kept in step with the server in the background. Nothing here is ever a failure — an
            // unreachable server costs nothing locally, so the worst case is "optional", never "missing".
            let cloud=r["team_cloud"] as? [String:Any] ?? [:]
            let macs=max((cloud["hosts"] as? [Any])?.count ?? 0,1)
            let lastOK=cloud["last_ok"] as? String ?? ""
            let lastError=cloud["last_error"] as? String ?? ""
            let waiting=cloud["outbox_pending_since"] as? String ?? ""
            // An error outranks an older success: a Mac that synced this morning and has been failing since
            // lunch used to read "son eşitleme 09:14" and nothing else (Codex, 10 Sep 2026, P1 #8 note).
            if !lastError.isEmpty {
                let since=lastOK.isEmpty ? "" : " · son başarılı eşitleme "+syncClock(lastOK)
                return SetupCheck(id:"team",title:"Ekip bilgi tabanı",state:.optional,hint:"bulut şu an erişilemiyor (\(lastError))"+(since.isEmpty ? "; yerel bilgi korunuyor, bağlanınca eşitlenir" : since))
            }
            // …and a pending outbox outranks an older success for the same reason: a word taught at 12:34 that
            // is still here at 15:00 must not read "son eşitleme 09:14 ✓". Green means the team HAS it.
            if !waiting.isEmpty {
                return SetupCheck(id:"team",title:"Ekip bilgi tabanı",state:.optional,
                                  hint:"ekip bulutu · \(macs) Mac · eşitleme bekliyor · \(syncClock(waiting))’ten beri")
            }
            if !lastOK.isEmpty { return SetupCheck(id:"team",title:"Ekip bilgi tabanı",state:.ok,hint:"ekip bulutu · \(macs) Mac · son eşitleme "+syncClock(lastOK)) }
            return SetupCheck(id:"team",title:"Ekip bilgi tabanı",state:.optional,hint:"ekip bulutu · ilk eşitleme bekleniyor")
        case "team": return SetupCheck(id:"team",title:"Ekip klasörü",state:.ok,hint:"ortak bilgi tabanı: "+root)
        case "icloud": return SetupCheck(id:"team",title:"Ekip klasörü",state:.optional,hint:"seçilmedi · iCloud Drive kullanılıyor (yalnız kendi Mac’leriniz arasında; ekip için Ayarlar → Sistem → Ekip klasörü)")
        default: return SetupCheck(id:"team",title:"Ekip klasörü",state:.missing,hint:"yok · iCloud Drive kapalı ve ekip klasörü seçilmedi: profiller, kelimeler ve raporlar paylaşılmıyor · Ayarlar → Sistem → Ekip klasörü")
        }
    }
    /// `2026-09-10T21:40:03.512345+00:00` → `00:40` in the user's own time zone. Python writes microseconds,
    /// which ISO8601DateFormatter refuses, so they are cut before parsing; an unparseable stamp falls back to
    /// the UTC clock inside the string rather than to nothing.
    static func syncClock(_ iso:String)->String {
        guard let date=syncDate(iso) else { return String(iso.dropFirst(11).prefix(5)) }
        let clock=DateFormatter(); clock.dateFormat="HH:mm"
        return clock.string(from:date)
    }
    /// The same parse as a `Date`, for the places that need to know how OLD a stamp is rather than how to
    /// print it (the outbox's "…'ten beri", the flush loop adopting the Python side's `since`).
    static func syncDate(_ iso:String)->Date? {
        var text=iso
        if let dot=text.firstIndex(of:"."), let end=text[dot...].firstIndex(where:{ $0=="+" || $0=="-" || $0=="Z" }) { text.removeSubrange(dot..<end) }
        let parser=ISO8601DateFormatter(); parser.formatOptions=[.withInternetDateTime]
        return parser.date(from:text)
    }
    /// `bundled`/`bundleVersion` come from `runtime.json`. A downloaded package has no checkout behind it, so
    /// the two rows that talk about one have to go: "İmzalama izni" names a script in a repo the user does not
    /// have, and "Sürüm" would offer a git update that cannot run. The version row keeps its `update` id and
    /// reads the package version instead — the bundle update channel fills the rest of it in.
    static func serviceChecks(_ r:[String:Any],repo:String="",divergedNotice:String="",bundled:Bool=false,bundleVersion:String="")->[SetupCheck] {
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
        // A package is never behind its own checkout and can never diverge from one: only the bundle channel
        // can say it is out of date, and it does that through the same `update_behind` field.
        let currentHint = bundled ? "Paket sürümü "+(bundleVersion.isEmpty ? "—" : bundleVersion) : "güncel"
        var out:[SetupCheck]=[
            SetupCheck(id:"key",title:"OpenRouter anahtarı",state:keyState,hint:keyHint),
            SetupCheck(id:"glossary",title:"Proje sözlüğü",state:glossary>0 ? .ok : .optional,hint:glossary>0 ? "\(glossary) terim · \(shared ? "iCloud Drive ile paylaşılıyor" : "yalnız bu Mac")" : "glossary.jsonl içe aktarın; iCloud Drive ile bütün Mac’lere yayılır"),
        ]
        if !bundled { out.append(SetupCheck(id:"signing",title:"İmzalama izni",state:signing ? .ok : .missing,hint:signing ? "verildi" : signingFix(repo:repo))) }
        let team=teamRootCheck(r); let effect=teamEffectTail(r)
        out.append(effect.isEmpty ? team : SetupCheck(id:team.id,title:team.title,state:team.state,hint:team.hint+effect))
        out.append(SetupCheck(id:"update",title:bundled ? "Paket sürümü" : "Sürüm",
                              state:(diverged && !bundled) ? .missing : (!updateError.isEmpty ? .optional : (behind==0 ? .ok : .missing)),
                              hint:(diverged && !bundled) ? divergedLine : (!updateError.isEmpty ? "kontrol edilemedi · "+updateError : (behind==0 ? currentHint : "\(behind) değişiklik geride · kenar çubuğundan güncelleyin"))))
        out.append(reportsCheck(r))
        if let quality=qualityCheck(r) { out.append(quality) }
        return out
    }
}
