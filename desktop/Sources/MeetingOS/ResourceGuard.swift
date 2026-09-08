import Foundation
import Darwin
struct ResourceGuard {
    static func budget(physical:UInt64)->UInt64 { min(10*1024*1024*1024,physical/4) }
    static func footprint(pid:pid_t)->UInt64? {
        var info=rusage_info_v2()
        let result=withUnsafeMutablePointer(to:&info) { pointer in
            proc_pid_rusage(pid,RUSAGE_INFO_V2,UnsafeMutableRawPointer(pointer).assumingMemoryBound(to:rusage_info_t?.self))
        }
        return result==0 ? info.ri_phys_footprint:nil
    }
}
