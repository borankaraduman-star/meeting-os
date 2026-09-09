import Foundation

/// Hands-free recording around a Zoom meeting window. Pure state machine, polled every refresh (~2 s):
/// starts after the meeting window has been open for a short confirmation period, and stops an auto-started
/// recording once the window has been gone for a full grace period so a flicker never cuts a meeting short.
struct ZoomAutoRecord: Equatable {
    enum Action: Equatable { case start, stop }
    static let confirmSeconds:TimeInterval=10
    static let graceSeconds:TimeInterval=300   // screen shares and Space switches hide the window for minutes
    private(set) var openSince:Date?
    private(set) var closedSince:Date?
    private(set) var autoStarted=false

    /// `meetingLikely`: Zoom is still running and the microphone is in use — never end a call on window heuristics alone.
    mutating func evaluate(zoomOpen:Bool,meetingLikely:Bool=false,recording:Bool,busy:Bool,enabled:Bool,now:Date=Date())->Action? {
        if !recording && autoStarted { autoStarted=false; closedSince=nil }   // user ended it, or the capture finished
        guard enabled else { openSince=nil; closedSince=nil; return nil }
        if recording {
            openSince=nil
            guard autoStarted else { return nil }
            if zoomOpen || meetingLikely { closedSince=nil; return nil }
            if closedSince==nil { closedSince=now; return nil }
            if now.timeIntervalSince(closedSince!) >= Self.graceSeconds { closedSince=nil; autoStarted=false; return .stop }
            return nil
        }
        closedSince=nil
        guard zoomOpen, !busy else { openSince=nil; return nil }
        if openSince==nil { openSince=now; return nil }
        if now.timeIntervalSince(openSince!) >= Self.confirmSeconds { openSince=nil; autoStarted=true; return .start }
        return nil
    }
}
