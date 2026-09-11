import Foundation

/// "I taught it" and "the team has it" are two different things, and until 1.2.78 only the first one was ever
/// true on purpose. A teach called `team_cloud.sync_async` — a daemon thread inside a bridge process that
/// exits the moment it has answered — so delivery was a hope, and the real guarantee was app launch and the
/// hourly housekeeping pass (Codex, 10 Sep 2026, P1 #8).
///
/// The Python side now leaves a promise on disk (`team-outbox.json`) before it asks for a pass. This is the
/// other half: the ONE background loop that keeps that promise, owned by the app, next to `heartbeatIfDue`.
/// Pure decisions only — no timer of its own, no bridge call, no state.
enum TeamOutbox {
    /// A teach is rarely alone: naming four voices in a row is four changes in twenty seconds, and each one
    /// would otherwise be its own network pass. The loop waits this long after the LAST change instead.
    static let settle:TimeInterval=20
    /// Still pending after a flush (the server was down, the budget ran out): try again on this beat. The
    /// target is "available on the other Mac in under a minute" when the network is there, and "eventually,
    /// without anybody noticing" when it is not.
    static let retry:TimeInterval=300

    /// May the app spend a slow-bridge call on a team flush right now?
    ///
    /// `dirtySince` is when this Mac last learned something the team has not seen (nil = nothing owed);
    /// `lastAttempt` is the last flush this app started, whatever came of it. Never while a recording is on:
    /// the one thing that outranks the team is the meeting the user is in.
    static func shouldFlush(now:Date=Date(),dirtySince:Date?,lastAttempt:Date?,recording:Bool)->Bool {
        guard !recording, let dirty=dirtySince else { return false }
        guard now.timeIntervalSince(dirty) >= settle else { return false }
        guard let last=lastAttempt else { return true }
        return now.timeIntervalSince(last) >= retry
    }
}
