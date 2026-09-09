import Foundation

/// Moments marked with ⌘M while recording. Written as one JSON line each into the capture folder so the
/// backend can attach them to the meeting when the recording is finalized.
struct Marker:Identifiable, Equatable {
    let seconds:Double; let kind:String
    var id:String { "\(kind)@\(seconds)" }
    var label:String { Marker.labels[kind] ?? "An" }
    var time:String { String(format:"%02d:%02d",Int(seconds)/60,Int(seconds)%60) }
    static let labels=["important":"An","decision":"Karar","task":"Görev","later":"Sonra"]
}

enum Markers {
    static func parse(_ metadata:[String:Any])->[Marker] {
        (metadata["markers"] as? [[String:Any]] ?? []).compactMap { d in
            guard let s=d["seconds"] as? Double, let k=d["kind"] as? String else { return nil }
            return Marker(seconds:s,kind:k)
        }
    }
    /// Markers that fall inside a paragraph, with a one-second grace so a mark pressed just after a sentence still lands on it.
    static func inBlock(_ markers:[Marker],start:Double,end:Double)->[Marker] { markers.filter { $0.seconds>=start-1 && $0.seconds<=end+1 } }
    static func line(seconds:Double,kind:String,now:Date=Date())->String {
        let payload:[String:Any]=["seconds":(seconds*10).rounded()/10,"kind":kind,"created":ISO8601DateFormatter().string(from:now)]
        return (try? String(data:JSONSerialization.data(withJSONObject:payload),encoding:.utf8)) ?? "{}"
    }
}
