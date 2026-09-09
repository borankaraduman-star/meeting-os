import SwiftUI

struct RelatedTask:Identifiable, Equatable {
    let id:String; let title:String; let meetingTitle:String; let state:String; let owner:String; let due:String; let similarity:Double; let supersededBy:String
    init(_ d:[String:Any]) { id=d["id"] as? String ?? ""; title=d["title"] as? String ?? ""; meetingTitle=d["meeting_title"] as? String ?? ""; state=d["state"] as? String ?? ""; owner=d["owner"] as? String ?? ""; due=d["due_text"] as? String ?? ""; similarity=d["similarity"] as? Double ?? 0; supersededBy=d["superseded_by"] as? String ?? "" }
}
struct PreviousDecision:Identifiable, Equatable {
    let id:String; let meetingTitle:String; let text:String; let similarity:Double
    init(_ d:[String:Any]) { meetingTitle=d["meeting_title"] as? String ?? ""; text=d["text"] as? String ?? ""; similarity=d["similarity"] as? Double ?? 0; id=meetingTitle+"|"+text }
}
/// Cross-meeting links for the selected meeting: tasks seen before, decisions that changed.
struct Continuity:Equatable {
    var relatedByTask:[String:[RelatedTask]]=[:]
    var historyByDecision:[String:[PreviousDecision]]=[:]
    static func parse(_ d:[String:Any])->Continuity {
        var c=Continuity()
        for r in d["related_tasks"] as? [[String:Any]] ?? [] { if let t=r["task"] as? String { c.relatedByTask[t]=(r["related"] as? [[String:Any]] ?? []).map(RelatedTask.init) } }
        for h in d["decision_history"] as? [[String:Any]] ?? [] { if let t=h["text"] as? String { c.historyByDecision[t]=(h["previous"] as? [[String:Any]] ?? []).map(PreviousDecision.init) } }
        return c
    }
}
