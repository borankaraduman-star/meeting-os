/// Each child owns the verdict its termination handler will read. Recorder and background jobs may overlap;
/// neither a new launch nor another child's cancellation may rewrite that verdict.
final class JobRun {
    var canceled=false
    var resourceFailure=""

    struct Completion {
        let succeeded:Bool
        let failure:String?
    }

    func completion(exitStatus:Int32,log:String)->Completion {
        let failed=exitStatus != 0 || !resourceFailure.isEmpty
        return Completion(succeeded:!failed && !canceled,
                          failure:failed && !canceled ? (resourceFailure.isEmpty ? log : resourceFailure) : nil)
    }
}

final class JobLifecycles {
    private(set) var job:JobRun?

    func begin(recording:Bool)->JobRun {
        let run=JobRun()
        if !recording { job=run }
        return run
    }

    func finish(_ run:JobRun) {
        if job === run { job=nil }
    }
}
