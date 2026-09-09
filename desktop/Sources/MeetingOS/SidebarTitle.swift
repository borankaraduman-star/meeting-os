import Foundation

/// What the single name field in the sidebar is for right now — or nothing at all.
enum SidebarTitleMode:String { case hidden, seed, rename }

/// The sidebar used to keep a name field on screen at all times. It is only useful in two moments: before a
/// recording starts (Model.start reads `title` once) and while a saved meeting still carries the timestamp
/// name start() falls back to. Everywhere else it is a control nobody touches, so it is hidden.
enum SidebarTitle {
    /// start() names an unnamed meeting "9 Eyl 2026 14:05"; the first summary bullet later replaces it.
    /// Meetings recorded by an older build carry that build's English default, "Sep 9, 2026 at 4:45 AM",
    /// and they are just as unnamed — so they get the rename field too.
    static func isTimestamp(_ title:String)->Bool { turkishTimestamp(title) || englishTimestamp(title) }
    private static func turkishTimestamp(_ title:String)->Bool {
        let parts=title.split(separator:" ",omittingEmptySubsequences:true)
        guard parts.count==4, parts[0].count<=2, parts[0].allSatisfy(\.isNumber), parts[2].count==4, parts[2].allSatisfy(\.isNumber) else { return false }
        guard parts[1].allSatisfy({ $0.isLetter || $0=="." }) else { return false }
        let clock=parts[3].split(separator:":",omittingEmptySubsequences:false)
        return clock.count==2 && clock.allSatisfy { !$0.isEmpty && $0.count<=2 && $0.allSatisfy(\.isNumber) }
    }
    /// "Sep 9, 2026 at 4:45 AM" and its 24-hour twin "Sep 9, 2026 at 16:45". The word "at" is what keeps a
    /// real title ("Sync with Bob at 3:00 PM") out: its second word is not a day number.
    private static func englishTimestamp(_ title:String)->Bool {
        let parts=title.split(whereSeparator:\.isWhitespace)   // newer formatters put a narrow no-break space before AM/PM
        guard parts.count==5 || parts.count==6, parts[3]=="at" else { return false }
        guard parts[0].count>=3, parts[0].allSatisfy({ $0.isLetter || $0=="." }) else { return false }
        let day=parts[1].hasSuffix(",") ? parts[1].dropLast() : parts[1][...]
        guard !day.isEmpty, day.count<=2, day.allSatisfy(\.isNumber) else { return false }
        guard parts[2].count==4, parts[2].allSatisfy(\.isNumber) else { return false }
        let clock=parts[4].split(separator:":",omittingEmptySubsequences:false)
        guard clock.count==2, clock.allSatisfy({ !$0.isEmpty && $0.count<=2 && $0.allSatisfy(\.isNumber) }) else { return false }
        return parts.count==5 || parts[5]=="AM" || parts[5]=="PM"
    }
    /// `selectedTitle` is nil when no meeting is on screen. A recording or busy app hides the field: the
    /// running meeting's name is already fixed and the record button is disabled anyway.
    static func mode(recording:Bool,busy:Bool,selectedTitle:String?)->SidebarTitleMode {
        if recording || busy { return .hidden }
        guard let title=selectedTitle else { return .seed }
        return isTimestamp(title) ? .rename : .hidden
    }
}
