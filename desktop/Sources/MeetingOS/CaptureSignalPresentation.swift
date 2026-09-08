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

        return "\(firstLine)\nMikrofon: \(mic)\nSistem: \(system)"
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
