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
}

struct ReportSettings:Equatable {
    /// `userName` labels the microphone speaker and drives the "Bana ait" task filter. The fallback matches
    /// reports.DEFAULT_USER_NAME so a database recorded before the setting existed keeps matching; the bridge
    /// overwrites it with the real value on the first `report_settings` call.
    var shareReports:Bool; var shareText:Bool; var autoUpdate:Bool; var reportDir:String; var audioRetentionDays:Int=30; var userName:String="Boran"
    static func parse(_ d:[String:Any])->ReportSettings {
        ReportSettings(shareReports:d["share_reports"] as? Bool ?? true,shareText:d["share_text"] as? Bool ?? false,autoUpdate:d["auto_update"] as? Bool ?? false,reportDir:d["report_dir"] as? String ?? "",audioRetentionDays:d["audio_retention_days"] as? Int ?? 30,userName:d["user_name"] as? String ?? "Boran")
    }
    var changes:[String:Any] { ["share_reports":shareReports,"share_text":shareText,"auto_update":autoUpdate,"report_dir":reportDir,"audio_retention_days":audioRetentionDays,"user_name":userName] }
}
