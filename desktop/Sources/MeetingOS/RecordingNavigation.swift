// Automatic navigation is a one-shot intent, not a property of recording.
struct RecordingNavigation {
    private var pending=false
    mutating func begin() { pending=true }
    mutating func selectionChanged() { pending=false }
    mutating func cancel() { pending=false }
    mutating func resolve(active:String)->String? {
        guard pending else { return nil }
        pending=false
        return active
    }
}
