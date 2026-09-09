import EventKit
import Foundation

/// One-tap hand-off of a meeting task into Apple Reminders (default list). Read/write only for reminders;
/// the calendar store stays read-only. Due text from the transcript goes into the note, never guessed into a date.
enum RemindersBridge {
    static let store=EKEventStore()
    static var authorized:Bool {
        if #available(macOS 14,*) { return EKEventStore.authorizationStatus(for:.reminder)==EKAuthorizationStatus.fullAccess }
        return EKEventStore.authorizationStatus(for:.reminder)==EKAuthorizationStatus.authorized
    }
    static func requestAccess(_ done:@escaping (Bool)->Void) {
        if #available(macOS 14,*) { store.requestFullAccessToReminders { ok,_ in DispatchQueue.main.async { done(ok) } } }
        else { store.requestAccess(to:.reminder) { ok,_ in DispatchQueue.main.async { done(ok) } } }
    }
    /// Note body shown under the reminder: where the task came from and what the meeting said about timing.
    static func note(meetingTitle:String,owner:String,due:String)->String {
        var lines=["Meeting OS · \(meetingTitle.isEmpty ? "toplantı" : meetingTitle)"]
        if !owner.isEmpty { lines.append("Sahip: \(owner)") }
        if !due.isEmpty { lines.append("Zaman: \(due)") }
        return lines.joined(separator:"\n")
    }
    static func add(title:String,meetingTitle:String,owner:String,due:String) throws {
        let r=EKReminder(eventStore:store)
        r.title=title; r.notes=note(meetingTitle:meetingTitle,owner:owner,due:due)
        guard let list=store.defaultCalendarForNewReminders() else { throw NSError(domain:"MeetingOS",code:1,userInfo:[NSLocalizedDescriptionKey:"Hatırlatıcılar’da varsayılan liste bulunamadı"]) }
        r.calendar=list
        try store.save(r,commit:true)
    }
}
