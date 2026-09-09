import Foundation

/// What the single name field in the sidebar is for right now — or nothing at all.
enum SidebarTitleMode:String { case hidden, seed, rename }

/// The sidebar used to keep a name field on screen at all times. It is only useful in two moments: before a
/// recording starts (Model.start reads `title` once) and while a saved meeting still carries the timestamp
/// name start() falls back to. Everywhere else it is a control nobody touches, so it is hidden.
enum SidebarTitle {
    /// start() names an unnamed meeting "9 Eyl 2026 14:05"; the first summary bullet later replaces it.
    static func isTimestamp(_ title:String)->Bool {
        let parts=title.split(separator:" ",omittingEmptySubsequences:true)
        guard parts.count==4, parts[0].count<=2, parts[0].allSatisfy(\.isNumber), parts[2].count==4, parts[2].allSatisfy(\.isNumber) else { return false }
        guard parts[1].allSatisfy({ $0.isLetter || $0=="." }) else { return false }
        let clock=parts[3].split(separator:":",omittingEmptySubsequences:false)
        return clock.count==2 && clock.allSatisfy { !$0.isEmpty && $0.count<=2 && $0.allSatisfy(\.isNumber) }
    }
    /// `selectedTitle` is nil when no meeting is on screen. A recording or busy app hides the field: the
    /// running meeting's name is already fixed and the record button is disabled anyway.
    static func mode(recording:Bool,busy:Bool,selectedTitle:String?)->SidebarTitleMode {
        if recording || busy { return .hidden }
        guard let title=selectedTitle else { return .seed }
        return isTimestamp(title) ? .rename : .hidden
    }
}
