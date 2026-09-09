import Foundation

/// The app must never compete with the meeting it is recording. Recording itself stays responsive;
/// every other job (upload, identity, analysis, documents) runs below normal, and below everything
/// else while a Zoom meeting window is on screen.
enum JobPriority {
    static func isRealtime(_ args:[String])->Bool { args.first=="record" }
    /// `idle` marks a job nobody asked for right now (the retry queue): it takes the same treatment as a job
    /// running under a live Zoom meeting, so the Mac stays entirely the user's the moment they touch it.
    static func qos(args:[String],zoomOpen:Bool,idle:Bool=false)->QualityOfService {
        if isRealtime(args) { return .userInitiated }
        return (zoomOpen || idle) ? .background : .utility
    }
    /// Extra environment for the job: the Python side lowers its own nice level and uploads one piece at a time.
    static func environment(args:[String],zoomOpen:Bool,idle:Bool=false)->[String:String] {
        (!isRealtime(args) && (zoomOpen || idle)) ? ["MEETING_OS_LOW_PRIORITY":"1"] : [:]
    }
}

/// Idle cadence for the 2-second poll: every tick while something moves, every third tick otherwise.
enum RefreshCadence {
    static func shouldRefresh(tick:Int,recording:Bool,busy:Bool,active:Bool)->Bool {
        if recording || busy || active { return true }
        return tick % 3 == 0
    }
}
