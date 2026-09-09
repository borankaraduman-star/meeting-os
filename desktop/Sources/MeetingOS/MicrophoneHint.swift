import Foundation
import IOKit

struct MicrophoneHint {
    static func current() -> String {
        let service=IOServiceGetMatchingService(kIOMainPortDefault,IOServiceMatching("IOPMrootDomain"))
        guard service != 0 else { return "" }
        defer { IOObjectRelease(service) }
        let closed=IORegistryEntryCreateCFProperty(service,"AppleClamshellState" as CFString,kCFAllocatorDefault,0)?.takeRetainedValue() as? Bool
        return closed == true ? "Kapak kapalı · dahili mikrofon kapalı, sistem sesi kaydediliyor." : ""
    }
}
