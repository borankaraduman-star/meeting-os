import Foundation

/// One-click updates from the GitHub branch. The check is a `git fetch` done by the backend; the update
/// itself runs in scripts/update.sh after the app quits, then relaunches the rebuilt, re-signed app.
struct UpdateInfo:Equatable {
    let available:Bool; let behind:Int; let subjects:[String]; let error:String; let local:String; let remote:String; let dirty:Bool
    static func parse(_ d:[String:Any])->UpdateInfo {
        UpdateInfo(available:d["available"] as? Bool ?? false,behind:d["behind"] as? Int ?? 0,subjects:d["subjects"] as? [String] ?? [],error:d["error"] as? String ?? "",local:d["local"] as? String ?? "",remote:d["remote"] as? String ?? "",dirty:d["dirty"] as? Bool ?? false)
    }
    var headline:String {
        if !error.isEmpty { return error }
        if available { return "Yeni sürüm hazır · \(behind) değişiklik" + (subjects.first.map { " · " + $0 } ?? "") }
        if dirty { return "Yerel değişiklikler var; otomatik güncelleme kapalı" }
        return "Güncel (\(local))"
    }
    /// The sidebar keeps one line, not a card: "Sürüm 1.2.27 · güncel". `version` is
    /// CFBundleShortVersionString (empty in a plain `swift build`), so the git hash stands in for it.
    static func sidebarLine(version:String,info:UpdateInfo?)->String {
        let name=version.isEmpty ? (info?.local ?? "") : version
        let prefix=name.isEmpty ? "Sürüm" : "Sürüm \(name)"
        guard let info else { return prefix+" · kontrol edilmedi" }
        if !info.error.isEmpty { return prefix+" · "+info.error }
        if info.available { return prefix+" · yeni sürüm hazır" }
        if info.dirty { return prefix+" · yerel değişiklik var" }
        return prefix+" · güncel"
    }
    static var appVersion:String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "" }
}

struct ReportSettings:Equatable {
    /// `userName` labels the microphone speaker and drives the "Bana ait" task filter. The fallback matches
    /// reports.DEFAULT_USER_NAME so a database recorded before the setting existed keeps matching; the bridge
    /// overwrites it with the real value on the first `report_settings` call.
    var shareReports:Bool; var shareText:Bool; var autoUpdate:Bool; var reportDir:String; var audioRetentionDays:Int=30; var autoRetry:Bool=true; var userName:String="Boran"
    /// Shared team folder (empty = off): the glossary is merged into it and reports are written there instead
    /// of the personal folder. A path the backend cannot see is refused, so the field reverts after saving.
    var teamDir:String=""; var shareGlossary:Bool=true
    static func parse(_ d:[String:Any])->ReportSettings {
        ReportSettings(shareReports:d["share_reports"] as? Bool ?? true,shareText:d["share_text"] as? Bool ?? false,autoUpdate:d["auto_update"] as? Bool ?? false,reportDir:d["report_dir"] as? String ?? "",audioRetentionDays:d["audio_retention_days"] as? Int ?? 30,autoRetry:d["auto_retry"] as? Bool ?? true,userName:d["user_name"] as? String ?? "Boran",teamDir:d["team_dir"] as? String ?? "",shareGlossary:d["share_glossary"] as? Bool ?? true)
    }
    var changes:[String:Any] { ["share_reports":shareReports,"share_text":shareText,"auto_update":autoUpdate,"report_dir":reportDir,"audio_retention_days":audioRetentionDays,"auto_retry":autoRetry,"user_name":userName,"team_dir":teamDir,"share_glossary":shareGlossary] }
}
