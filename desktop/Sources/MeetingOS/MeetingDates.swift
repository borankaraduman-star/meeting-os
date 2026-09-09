import Foundation

/// Sidebar grouping and human time labels for meetings, from the ISO `created` stamp the backend stores.
enum MeetingDates {
    static let parser:ISO8601DateFormatter = { let f=ISO8601DateFormatter(); f.formatOptions=[.withInternetDateTime,.withFractionalSeconds]; return f }()
    static let plain:ISO8601DateFormatter = { let f=ISO8601DateFormatter(); f.formatOptions=[.withInternetDateTime]; return f }()
    static func date(_ created:String)->Date? { parser.date(from:created) ?? plain.date(from:created) }
    /// "Bugün", "Dün", "Bu hafta", "Daha eski" (calendar days, Monday-based week).
    static func group(_ created:String,now:Date=Date(),calendar:Calendar = .current)->String {
        guard let d=date(created) else { return "Daha eski" }
        if calendar.isDate(d,inSameDayAs:now) { return "Bugün" }
        if let y=calendar.date(byAdding:.day,value:-1,to:now), calendar.isDate(d,inSameDayAs:y) { return "Dün" }
        var cal=calendar; cal.firstWeekday=2
        if let start=cal.dateInterval(of:.weekOfYear,for:now)?.start, d>=start { return "Bu hafta" }
        return "Daha eski"
    }
    static let order=["Bugün","Dün","Bu hafta","Daha eski"]
    /// "2026-09-12" → Date at local midnight; nil for anything else.
    static func day(_ iso:String)->Date? {
        let f=DateFormatter(); f.locale=Locale(identifier:"en_US_POSIX"); f.dateFormat="yyyy-MM-dd"; f.timeZone=TimeZone.current
        return f.date(from:String(iso.prefix(10)))
    }
    /// "12 Eyl" / "12 Eyl 2025" for a calendar date.
    static func dayLabel(_ iso:String,now:Date=Date())->String {
        guard let d=day(iso) else { return iso }
        let f=DateFormatter(); f.locale=Locale(identifier:"tr_TR")
        f.dateFormat=Calendar.current.component(.year,from:d)==Calendar.current.component(.year,from:now) ? "d MMM" : "d MMM yyyy"
        return f.string(from:d)
    }
    static func isPast(_ iso:String,now:Date=Date())->Bool { day(iso).map { Calendar.current.startOfDay(for:$0) < Calendar.current.startOfDay(for:now) } ?? false }
    /// "Bugün 14:05", "Dün 09:30", "8 Eyl 14:05", "8 Eyl 2025".
    static func label(_ created:String,now:Date=Date(),calendar:Calendar = .current)->String {
        guard let d=date(created) else { return String(created.prefix(10)) }
        let tr=Locale(identifier:"tr_TR")
        let clock=DateFormatter(); clock.locale=tr; clock.calendar=calendar; clock.timeZone=calendar.timeZone; clock.dateFormat="HH:mm"
        let time=clock.string(from:d)
        switch group(created,now:now,calendar:calendar) {
        case "Bugün": return "Bugün \(time)"
        case "Dün": return "Dün \(time)"
        default:
            let sameYear=calendar.component(.year,from:d)==calendar.component(.year,from:now)
            let day=d.formatted(Date.FormatStyle(date:.abbreviated,time:.omitted,locale:tr,calendar:calendar))
            return sameYear ? "\(day.replacingOccurrences(of:" \(calendar.component(.year,from:d))",with:"")) \(time)" : day
        }
    }
}
