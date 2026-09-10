import Foundation

/// Bridge calls to the Python side run on their own GCD queue, at most two at a time, so a slow call
/// (disk stall, Keychain prompt, git fetch) can never exhaust Swift's cooperative thread pool and freeze
/// every `await` in the app. Durations are kept so the settings card can show poll latency.
enum Bridge {
    static let queue=DispatchQueue(label:"meetingos.bridge",qos:.utility,attributes:.concurrent)
    static let slots=DispatchSemaphore(value:2)
    static func call(_ runtime:Runtime,_ request:[String:Any]) async throws -> [String:Any] {
        try await withCheckedThrowingContinuation { cont in
            queue.async {
                slots.wait(); defer { slots.signal() }
                let started=Date()
                let result=Result { try invoke(runtime,request) }
                BridgeStats.shared.record(seconds:Date().timeIntervalSince(started),failed:(try? result.get())==nil)
                cont.resume(with:result)
            }
        }
    }
    /// The housekeeping sweep archives every finished meeting's audio to FLAC and can legitimately run for
    /// minutes. On the poll's queue it did two harmful things at once: it was killed at the ten-second
    /// watchdog, so the archive never finished and the same work was attempted again the next hour, and while
    /// it ran it held one of the two poll slots. Its own serial queue, its own deadline, and out of the
    /// latency window — a ten-minute sweep in the p95 would make the settings card's poll figure meaningless.
    static let slowQueue=DispatchQueue(label:"meetingos.bridge.slow",qos:.utility)
    static func callSlow(_ runtime:Runtime,_ request:[String:Any],timeout:TimeInterval = 600) async throws -> [String:Any] {
        try await withCheckedThrowingContinuation { cont in
            slowQueue.async { cont.resume(with:Result { try invoke(runtime,request,timeout:timeout) }) }
        }
    }
}

/// Rolling latency window of bridge calls. Pure arithmetic, testable.
final class BridgeStats: @unchecked Sendable {
    static let shared=BridgeStats()
    private let lock=NSLock(); private var samples:[Double]=[]; private(set) var failures=0; private(set) var slow=0
    let capacity:Int
    init(capacity:Int=200) { self.capacity=capacity }
    func record(seconds:Double,failed:Bool=false) {
        lock.lock(); defer { lock.unlock() }
        samples.append(seconds); if samples.count>capacity { samples.removeFirst(samples.count-capacity) }
        if failed { failures+=1 }; if seconds>1 { slow+=1 }
    }
    func percentile(_ p:Double)->Double? {
        lock.lock(); defer { lock.unlock() }
        guard !samples.isEmpty else { return nil }
        let sorted=samples.sorted(); let idx=min(sorted.count-1,max(0,Int((Double(sorted.count-1)*p).rounded())))
        return sorted[idx]
    }
    var summary:String {
        guard let p50=percentile(0.5), let p95=percentile(0.95) else { return "henüz ölçüm yok" }
        return String(format:"p50 %.0f ms · p95 %.0f ms · >1 sn: %d · hata: %d",p50*1000,p95*1000,slow,failures)
    }
    var snapshot:[String:Any] { ["p50_ms":(percentile(0.5) ?? 0)*1000,"p95_ms":(percentile(0.95) ?? 0)*1000,"slow":slow,"failures":failures] }
}
