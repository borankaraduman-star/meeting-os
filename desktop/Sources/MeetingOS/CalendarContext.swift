import EventKit
import Foundation

/// The calendar event that is happening while a recording starts: its title names the meeting,
/// its attendees are offered when naming speakers. Read-only; nothing is written to the calendar.
struct CalendarEvent: Equatable {
    let title:String; let attendees:[String]; let start:Date; let end:Date
    var payload:[String:Any] { ["title":title,"attendees":attendees,"start":ISO8601DateFormatter().string(from:start),"end":ISO8601DateFormatter().string(from:end)] }
}

enum CalendarContext {
    static let store=EKEventStore()
    static var authorized:Bool {
        if #available(macOS 14,*) { return EKEventStore.authorizationStatus(for:.event)==EKAuthorizationStatus.fullAccess }
        return EKEventStore.authorizationStatus(for:.event)==EKAuthorizationStatus.authorized
    }
    /// Ask once; the setting toggle calls this so the prompt never lands in the middle of a recording start.
    static func requestAccess(_ done:@escaping (Bool)->Void) {
        if #available(macOS 14,*) { store.requestFullAccessToEvents { ok,_ in DispatchQueue.main.async { done(ok) } } }
        else { store.requestAccess(to:.event) { ok,_ in DispatchQueue.main.async { done(ok) } } }
    }
    /// Synchronous on purpose: recording start must not wait on a permission dialog. Returns nil without access.
    private static var cache:(at:Date,event:CalendarEvent?)?
    /// Menu bar and panels ask often; EventKit is queried at most once a minute.
    static func currentCached(now:Date=Date())->CalendarEvent? {
        if let c=cache, now.timeIntervalSince(c.at)<60 { return c.event }
        let e=current(now:now); cache=(now,e); return e
    }
    static func current(now:Date=Date())->CalendarEvent? {
        guard authorized else { return nil }
        let predicate=store.predicateForEvents(withStart:now.addingTimeInterval(-3*3600),end:now.addingTimeInterval(3600),calendars:nil)
        let events=store.events(matching:predicate).filter { !$0.isAllDay }.map { e in
            Candidate(title:e.title ?? "",start:e.startDate,end:e.endDate,attendees:(e.attendees ?? []).filter { !$0.isCurrentUser && $0.participantType != .resource && $0.participantType != .room }.compactMap { participantName($0) })
        }
        return pick(events,now:now)
    }
    struct Candidate { let title:String; let start:Date; let end:Date; let attendees:[String] }
    /// The event covering `now` (5 min grace on both ends); among overlaps the one that started most recently.
    static func pick(_ events:[Candidate],now:Date)->CalendarEvent? {
        let grace:TimeInterval=5*60
        let live=events.filter { !$0.title.trimmingCharacters(in:.whitespaces).isEmpty && $0.start<=now.addingTimeInterval(grace) && $0.end>=now.addingTimeInterval(-grace) }
        guard let best=live.max(by:{ $0.start<$1.start }) else { return nil }
        var seen=Set<String>(); let names=best.attendees.filter { seen.insert($0.lowercased()).inserted }
        return CalendarEvent(title:String(best.title.trimmingCharacters(in:.whitespaces).prefix(120)),attendees:Array(names.prefix(30)),start:best.start,end:best.end)
    }
    static func participantName(_ p:EKParticipant)->String? {
        if let n=p.name, !n.isEmpty, !n.contains("@") { return n }
        return displayName(fromAddress:p.url.absoluteString)
    }
    /// "ayse.yilmaz@firma.com" → "Ayse Yilmaz"; nil for addresses that are only digits or noise.
    static func displayName(fromAddress address:String)->String? {
        let raw=address.replacingOccurrences(of:"mailto:",with:"")
        guard let local=raw.split(separator:"@").first, !local.isEmpty else { return nil }
        let parts=local.split(whereSeparator:{ "._-".contains($0) }).map(String.init).filter { $0.rangeOfCharacter(from:.letters) != nil }
        guard !parts.isEmpty else { return nil }
        return parts.map { $0.prefix(1).uppercased()+$0.dropFirst().lowercased() }.joined(separator:" ")
    }
}
