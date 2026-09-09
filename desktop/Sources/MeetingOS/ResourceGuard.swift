import Foundation
import Darwin
struct ResourceGuard {
    /// Only jobs that load a local model are stopped on OS memory-pressure events. Capture without live
    /// preview and the OpenRouter jobs (ffmpeg + HTTP) are light and must survive a warning.
    static func stopsOnPressure(jobArguments:[String])->Bool {
        guard let command=jobArguments.first else { return false }
        if command=="record" { return jobArguments.contains("--live") }
        return !["openrouter-finalize","openrouter-import"].contains(command)
    }
    /// What an OS memory-pressure event is allowed to stop. Recording owns a process slot of its own, so the
    /// only thing under pressure is the background job — there is deliberately no case that stops a recording:
    /// a meeting is never sacrificed for an analyze/retry/prepare/ask pass that happens to be running beside it.
    enum PressureAction { case none, terminateJob }
    static func pressureAction(hasJob:Bool,stopsOnPressure:Bool,recording:Bool,alreadyStopped:Bool)->PressureAction {
        guard hasJob, stopsOnPressure, !alreadyStopped else { return .none }
        return .terminateJob
    }
    static func budget(physical:UInt64)->UInt64 { min(10*1024*1024*1024,physical/4) }
    static func footprint(pid:pid_t)->UInt64? {
        var info=rusage_info_v2()
        let result=withUnsafeMutablePointer(to:&info) { pointer in
            proc_pid_rusage(pid,RUSAGE_INFO_V2,UnsafeMutableRawPointer(pointer).assumingMemoryBound(to:rusage_info_t?.self))
        }
        return result==0 ? info.ri_phys_footprint:nil
    }
}
