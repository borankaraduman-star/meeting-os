import Foundation
import CoreFoundation

public enum CaptureSignalPresentation {

    private static let maxSeconds: Double = 86400
    private static let staleThresholdSeconds: Double = 30

    public static func label(_ capture: [String: Any]) -> String {
        let state = capture["state"] as? String
        let signals = capture["signals"] as? [String: Any]

        let firstLine: String
        switch state {
        case "capturing":
            firstLine = "Kayıt: \(formattedTime(sanitizedSeconds(capture["seconds"])))"
        case "waiting":
            firstLine = "Ses akışı bekleniyor"
        case "error":
            firstLine = "Kayıt hatası"
        case "stopped":
            firstLine = "Kayıt durduruldu"
        default:
            firstLine = "Durum bilinmiyor"
        }

        let mic = describeSignal(signals, key: "mic")
        let system = describeSignal(signals, key: "system")

        let missingPreview = (capture["preview"] as? [String: Any])?["has_known_failures"] as? Bool == true
        let warning = missingPreview ? "\nCanlı metin eksik" : ""
        // The disk line only exists once the helper has journalled `low_disk`, so an ordinary meeting reads exactly as before.
        let disk = lowDisk(capture).map { "\n" + $0 } ?? ""
        return "\(firstLine)\nMikrofon: \(mic)\nSistem: \(system)" + warning + disk
    }

    /// "Disk azalıyor · 1,2 GB boş · kayıt 69 dk sonra durabilir" — built from the helper's `low_disk` journal
    /// line, which the bridge surfaces as `low_disk_bytes`. A number of minutes is the only form of this warning
    /// anyone can act on: "disk is filling up" during a meeting tells the user nothing about whether to stop.
    /// nil whenever the helper has not warned, so nothing is invented from a missing reading.
    public static func lowDisk(_ capture: [String: Any]) -> String? {
        guard let raw = extractDouble(capture["low_disk_bytes"]), raw.isFinite, raw >= 0 else { return nil }
        let free = Int(min(raw, 1e15))
        return "Disk azalıyor · \(StorageReport.format(bytes: free)) boş · kayıt \(DiskSpace.minutesLeft(freeBytes: free)) dk sonra durabilir"
    }

    /// Compact state for the floating panel dots: "ok", "silent", "stale" or "unknown".
    public static func dotState(_ capture: [String: Any], key: String) -> String {
        guard let entry = (capture["signals"] as? [String: Any])?[key] as? [String: Any], let state = entry["state"] as? String else { return "unknown" }
        if isStale(entry) { return "stale" }
        switch state { case "signal": return "ok"; case "digital_silence": return "silent"; default: return "unknown" }
    }

    private static func describeSignal(_ signals: [String: Any]?, key: String) -> String {
        guard let entry = signals?[key] as? [String: Any],
              let state = entry["state"] as? String else {
            return "Doğrulanamadı"
        }

        switch state {
        case "signal":
            return isStale(entry) ? "Güncel değil" : "Sinyal var"
        case "digital_silence":
            return isStale(entry) ? "Güncel değil" : "Sessiz"
        default:
            return "Doğrulanamadı"
        }
    }

    // An unparsable age is treated as stale rather than ignored, so a bad
    // reading is never presented as a currently-active signal.
    private static func isStale(_ entry: [String: Any]) -> Bool {
        guard let raw = entry["age_seconds"] else { return false }
        guard let age = extractDouble(raw), age.isFinite, age >= 0 else { return true }
        return age > staleThresholdSeconds
    }

    // Clamped before the Int conversion so malformed input (NaN, negative,
    // or absurdly large) can never overflow or underflow the result.
    private static func sanitizedSeconds(_ raw: Any?) -> Int {
        guard let value = extractDouble(raw), value.isFinite, value >= 0 else { return 0 }
        return Int(min(value, maxSeconds))
    }

    private static func extractDouble(_ value: Any?) -> Double? {
        guard let value, let number = value as? NSNumber else { return nil }
        // Foundation bridges JSON 0/1 to NSNumber that can pass `is Bool`.
        // Only CFBoolean is a boolean; ordinary numeric 0/1 are valid readings.
        guard CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
        return number.doubleValue
    }

    private static func formattedTime(_ totalSeconds: Int) -> String {
        let hours = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        let seconds = totalSeconds % 60
        if hours > 0 {
            return String(format: "%02d:%02d:%02d", hours, minutes, seconds)
        }
        return String(format: "%02d:%02d", minutes, seconds)
    }
}
