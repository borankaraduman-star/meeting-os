import Foundation

/// Disk arithmetic for recording. A meeting writes the microphone and the system output side by side and
/// lands at ≈1.04 GB per hour, so "how much longer can this record?" is a division and not a guess.
/// The capture helper journals `low_disk` below 3 GB and stops itself below 400 MB; these numbers exist so
/// the app can say the same thing in minutes, before the recording is the one that discovers it.
enum DiskSpace {
    /// Measured on finished meetings: mic + system, 16 kHz mono WAV chunks, before the FLAC archive pass.
    static let bytesPerHour: Double = 1_040_000_000
    /// Below this a full hour no longer fits, so ⌃⌥R says so first.
    static let warnBytes = 1_500_000_000
    /// The helper's own `diskStartBytes`: below this it refuses to open the files at all, so the app must not
    /// promise a recording it cannot get.
    static let refuseBytes = 600_000_000

    /// Minutes of recording the free space still holds, rounded down. Never negative.
    static func minutesLeft(freeBytes: Int) -> Int {
        guard freeBytes > 0 else { return 0 }
        return Int((Double(freeBytes) / bytesPerHour * 60).rounded(.down))
    }

    /// Free space on the volume that holds `url`, in bytes; nil when the volume cannot be read — an unreadable
    /// volume must never be reported as full, because that would refuse a recording over a failed query.
    static func free(at url: URL) -> Int? {
        // The data folder does not exist until the first job creates it, and a missing path answers nothing at
        // all — so the question is put to the nearest ancestor that does exist. Same volume, same answer.
        var probe = url.standardizedFileURL
        while true {
            if let values = try? probe.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey]),
               let capacity = values.volumeAvailableCapacityForImportantUsage { return Int(clamping: capacity) }
            let parent = probe.deletingLastPathComponent()
            guard parent.path != probe.path else { return nil }
            probe = parent
        }
    }

    /// The one line shown before a recording starts, or nil when there is room. A refusal and a warning read
    /// the same because the user's next move is the same either way: free some space.
    static func startNotice(freeBytes: Int?) -> String? {
        guard let freeBytes, freeBytes < warnBytes else { return nil }
        return "Disk dolu: en az 1,5 GB boş alan gerekir (kayıt ≈1 GB/saat) · \(StorageReport.format(bytes: freeBytes)) boş"
    }

    /// Only a genuinely full disk refuses; between 600 MB and 1,5 GB the user is warned and still gets the meeting.
    static func refuses(freeBytes: Int?) -> Bool {
        guard let freeBytes else { return false }   // unreadable volume: warn nothing, refuse nothing
        return freeBytes < refuseBytes
    }
}
