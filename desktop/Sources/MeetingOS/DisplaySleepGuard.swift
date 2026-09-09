import Foundation
import IOKit.pwr_mgt

/// System-audio capture runs through ScreenCaptureKit, which dies when every display sleeps
/// ("Failed to find any displays or windows to capture"). Hold a display-sleep assertion for the
/// duration of a recording; release it as soon as the recording ends.
enum DisplaySleepGuard {
    private static var assertion:IOPMAssertionID=0
    static var active:Bool { assertion != 0 }
    static func begin() {
        guard assertion==0 else { return }
        var id:IOPMAssertionID=0
        let ok=IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleDisplaySleep as CFString,IOPMAssertionLevel(kIOPMAssertionLevelOn),"Meeting OS kayıt sürüyor" as CFString,&id)
        if ok==kIOReturnSuccess { assertion=id }
    }
    static func end() {
        guard assertion != 0 else { return }
        IOPMAssertionRelease(assertion); assertion=0
    }
}
