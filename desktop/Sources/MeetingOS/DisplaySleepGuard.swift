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

/// Transcription and analysis are long, silent and unattended: a Mac left alone reaches its idle-sleep timer
/// and suspends the child mid-upload, and the user comes back to a half-finished meeting. Hold a *system*
/// idle-sleep assertion for as long as a job runs — never a display assertion, because keeping the screen
/// awake for a background job is rude and burns battery. A closed lid still sleeps; that is the user's choice.
enum JobSleepGuard {
    private static var assertion:IOPMAssertionID=0
    static var active:Bool { assertion != 0 }
    static func begin() {
        guard assertion==0 else { return }
        var id:IOPMAssertionID=0
        let ok=IOPMAssertionCreateWithName(kIOPMAssertionTypePreventUserIdleSystemSleep as CFString,IOPMAssertionLevel(kIOPMAssertionLevelOn),"Meeting OS: toplantı yazıya çevriliyor" as CFString,&id)
        if ok==kIOReturnSuccess { assertion=id }
    }
    static func end() {
        guard assertion != 0 else { return }
        IOPMAssertionRelease(assertion); assertion=0
    }
}
