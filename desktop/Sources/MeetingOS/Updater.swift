import Foundation

/// One-click updates from the GitHub branch. The check is a `git fetch` done by the backend; the update
/// itself runs in scripts/update.sh after the app quits, then relaunches the rebuilt, re-signed app.
struct UpdateInfo:Equatable {
    let available:Bool; let behind:Int; let subjects:[String]; let error:String; let local:String; let dirty:Bool
    /// A branch that carries commits GitHub has never seen cannot be fast-forwarded, so `scripts/update.sh`
    /// refuses and this Mac would otherwise sit on "güncel" forever while the setup card said "N değişiklik geride".
    /// `hint` is the bridge's own sentence when it has one; `ahead` is how many local commits caused it.
    let diverged:Bool; let ahead:Int; let hint:String
    static func parse(_ d:[String:Any])->UpdateInfo {
        UpdateInfo(available:d["available"] as? Bool ?? false,behind:d["behind"] as? Int ?? 0,subjects:d["subjects"] as? [String] ?? [],error:d["error"] as? String ?? "",local:d["local"] as? String ?? "",dirty:d["dirty"] as? Bool ?? false,diverged:d["diverged"] as? Bool ?? false,ahead:d["ahead"] as? Int ?? 0,hint:d["hint"] as? String ?? "")
    }
    /// The one sentence every screen uses for a diverged branch, so the sidebar, Ayarlar and the setup card agree.
    static let divergedMessage="Dal ayrışmış · yeni sürüm kurulamıyor · Boran’a bildirin"
    static func divergedText(ahead:Int,hint:String)->String {
        if !hint.isEmpty { return hint }
        return divergedMessage + (ahead>0 ? " · \(ahead) yerel değişiklik ileride" : "")
    }
    var divergedNotice:String { diverged ? Self.divergedText(ahead:ahead,hint:hint) : "" }
    /// Whether the "Güncelle ve yeniden başlat" button may appear: a diverged branch cannot be updated at all.
    var canUpdate:Bool { available && !diverged }
    var headline:String {
        if !error.isEmpty { return error }
        if diverged { return divergedNotice }
        if available { return "Yeni sürüm hazır · \(behind) değişiklik" + (subjects.first.map { " · " + $0 } ?? "") }
        if dirty { return "Yerel değişiklikler var; otomatik güncelleme kapalı" }
        return "Güncel (\(local))"
    }
    /// The sidebar keeps one line, not a card: "Sürüm <x.y.z> · güncel". `version` is
    /// CFBundleShortVersionString (empty in a plain `swift build`), so the git hash stands in for it.
    static func sidebarLine(version:String,info:UpdateInfo?)->String {
        let name=version.isEmpty ? (info?.local ?? "") : version
        let prefix=name.isEmpty ? "Sürüm" : "Sürüm \(name)"
        guard let info else { return prefix+" · kontrol edilmedi" }
        if !info.error.isEmpty { return prefix+" · "+info.error }
        if info.diverged { return prefix+" · "+info.divergedNotice }
        if info.available { return prefix+" · yeni sürüm hazır" }
        if info.dirty { return prefix+" · yerel değişiklik var" }
        return prefix+" · güncel"
    }
    static var appVersion:String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "" }
}

/// What `update-status.json` (written by scripts/update.sh, read back through the `update_status` bridge call)
/// should say in the "Son durum" line. A `running` state is normally silent — the app was quitting when it was
/// written — but a `running` older than half an hour means the updater died between two steps and nobody would
/// ever be told: the rebuild has to be finished by hand.
enum UpdateStatusLine {
    static let stallSeconds:TimeInterval=30*60
    static let stalledMessage="Güncelleme yarıda kalmış olabilir · sh scripts/update.sh"
    /// scripts/update.sh writes `date '+%Y-%m-%d %H:%M:%S'`: local time, no zone.
    static func parseTime(_ raw:String)->Date? {
        let f=DateFormatter(); f.dateFormat="yyyy-MM-dd HH:mm:ss"; f.locale=Locale(identifier:"en_US_POSIX"); f.timeZone=TimeZone.current
        return f.date(from:raw)
    }
    /// The bundle channel's own states (meeting_os/updater.py): the download is minutes long and the app is
    /// still open for it, so unlike a git rebuild these are worth saying out loud.
    static let downloadingPrefix="Yeni sürüm indiriliyor"
    static let swappingMessage="Yeni sürüm yerine konuyor · uygulama yeniden açılacak"
    /// nil = say nothing. `failed` is also worth a notification; the caller decides that from the state.
    /// `percent` is `update-status.json`'s `percent` key (bundle channel only, 0 when it is not there); the
    /// worker also writes the same number into `message`, so a caller that does not read the key still shows
    /// a percentage.
    static func line(state:String,message:String,time:String,percent:Int=0,now:Date=Date())->String? {
        switch state {
        case "done": return "Güncelleme tamam · "+message
        case "failed": return "Güncelleme başarısız · "+message
        case "refused": return "Güncelleme yapılmadı · "+message   // a recording, local edits or a second run: not a failure, no notification
        case "downloading":
            if percent>0 { return downloadingPrefix+" · %\(percent)" }
            return message.isEmpty ? downloadingPrefix : message
        case "verifying": return "Paket doğrulanıyor"
        case "extracting": return "Paket açılıyor"
        case "swapping": return message.isEmpty ? swappingMessage : message
        case "running":
            guard let started=parseTime(time), now.timeIntervalSince(started) >= stallSeconds else { return nil }
            return stalledMessage
        default: return nil
        }
    }
    /// The bundle swap moves the running .app aside, so the app has to be gone first: scripts/swap-update.sh
    /// waits up to 60 s for the pid and then gives up, leaving the old version installed. `swapping` in the
    /// status file is the app's cue to quit itself.
    static func shouldQuit(state:String)->Bool { state=="swapping" }
}

/// Whether this copy runs from a self-contained app bundle (docs/BUNDLE.md) rather than a git checkout, read
/// straight from `Contents/Resources/runtime.json`. `Runtime` in App.swift decodes the same file for the
/// python/repo paths; this reads it again, on its own, so the update path never has to wait on that struct
/// gaining a field — and so it can be tested without a real bundle (`override`).
enum BundleInfo {
    /// Test seam: a runtime.json dictionary to use instead of the running bundle's.
    static var override:[String:Any]?
    static var runtime:[String:Any]? {
        if let override { return override }
        guard let url=Bundle.main.resourceURL?.appendingPathComponent("runtime.json"),
              let data=try? Data(contentsOf:url),
              let dict=try? JSONSerialization.jsonObject(with:data) as? [String:Any] else { return nil }
        return dict
    }
    static var bundled:Bool { runtime?["bundled"] as? Bool == true }
    /// The bundle the app is running FROM, which is where the swap puts the new one: an app opened from
    /// ~/Downloads updates in ~/Downloads. Never /Applications by name — the swap script uses no sudo and
    /// must not need a writable /Applications.
    static var appPath:String { Bundle.main.bundleURL.path }
    /// The `update_start` bridge request. The git channel needs nothing; the bundle channel needs the path to
    /// replace and the pid to wait for, because scripts/swap-update.sh moves the bundle only after the app
    /// that was running it has exited.
    static func updateStartRequest(bundled:Bool?=nil,appPath:String?=nil,pid:Int32?=nil)->[String:Any] {
        var request:[String:Any]=["action":"update_start"]
        guard bundled ?? Self.bundled else { return request }
        request["app_path"]=appPath ?? Self.appPath
        request["pid"]=Int(pid ?? ProcessInfo.processInfo.processIdentifier)
        return request
    }
}

struct ReportSettings:Equatable {
    /// `userName` labels the microphone speaker and drives the "Bana ait" task filter. It starts empty on
    /// purpose: a pre-filled name is a name the second person to open this app never notices is wrong, and
    /// their voice would be filed under somebody else. Empty means "ask"; the bridge writes the real value.
    var shareReports:Bool; var shareText:Bool; var autoUpdate:Bool; var reportDir:String; var audioRetentionDays:Int=30; var autoRetry:Bool=true; var userName:String=""
    /// How long the TEXT of a meeting lives here: transcript, summary and tasks. 0 = never delete, and that is
    /// the default — audio can be given up, a transcript is the meeting. A horizon chosen up front is what
    /// makes it safe; deciding to wipe everything on the day something happens is not.
    var textRetentionDays:Int=0
    /// Shared team folder (empty = off): the glossary is merged into it and reports are written there instead
    /// of the personal folder. A path the backend cannot see is refused, so the field reverts after saving.
    var teamDir:String=""; var shareGlossary:Bool=true
    /// The team folder is one knowledge base: taught words and voice profiles go both ways by default. The way
    /// out of a single item is per row (a team word can be switched off, a person's team samples deleted); these
    /// two switch the whole exchange off for this Mac, in both directions.
    var shareWords:Bool=true; var shareProfiles:Bool=true
    /// May a measured experiment APPLY itself (1.2.85)? Off. The idle pass measures either way and writes the
    /// result down; with this off the setup card says "otomatik uygulama kapalı" and the user applies the
    /// recommendation deliberately. Nothing here leaves this Mac, and every promotion is one rollback away.
    var autoPromotePolicies:Bool=false
    static func parse(_ d:[String:Any])->ReportSettings {
        ReportSettings(shareReports:d["share_reports"] as? Bool ?? true,shareText:d["share_text"] as? Bool ?? false,autoUpdate:d["auto_update"] as? Bool ?? false,reportDir:d["report_dir"] as? String ?? "",audioRetentionDays:d["audio_retention_days"] as? Int ?? 30,autoRetry:d["auto_retry"] as? Bool ?? true,userName:d["user_name"] as? String ?? "",textRetentionDays:d["text_retention_days"] as? Int ?? 0,teamDir:d["team_dir"] as? String ?? "",shareGlossary:d["share_glossary"] as? Bool ?? true,shareWords:d["share_words"] as? Bool ?? true,shareProfiles:d["share_profiles"] as? Bool ?? true,autoPromotePolicies:d["auto_promote_policies"] as? Bool ?? false)
    }
    var changes:[String:Any] { ["share_reports":shareReports,"share_text":shareText,"auto_update":autoUpdate,"report_dir":reportDir,"audio_retention_days":audioRetentionDays,"auto_retry":autoRetry,"user_name":userName,"text_retention_days":textRetentionDays,"team_dir":teamDir,"share_glossary":shareGlossary,"share_words":shareWords,"share_profiles":shareProfiles,"auto_promote_policies":autoPromotePolicies] }
}
