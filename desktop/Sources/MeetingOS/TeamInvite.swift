import Foundation

/// Joining a team without a terminal (Boran, 10 Sep 2026: "kullanacak insanlar terminal yazamaz").
///
/// A teammate is sent a LINK (`meetingos://join?team=…`) on Slack or WhatsApp, or a FILE
/// (`Meeting OS Daveti.meetingos-invite`) when a chat app eats custom schemes. Clicking either one opens
/// Meeting OS, hands the text to the bridge's `team_join`, and that is the whole join. Nothing here parses
/// the payload itself — `meeting_os/team_cloud.py` owns that, so the app and the CLI can never disagree
/// about what a valid invite is. This file only recognises what an incoming URL *is*, and says in one line
/// where the team's knowledge actually goes.

/// Where this Mac's shared knowledge really lands, as the Ekip card states it on its first line. The three
/// share switches follow THIS, not `team_dir`: with the cloud configured `team_dir` is empty while everything
/// is being shared, which is exactly the P0 the 10 Sep 2026 review found (switches greyed out, data flowing).
struct TeamTarget:Equatable {
    enum Kind:String { case cloud, folder, off }
    let kind:Kind
    let line:String
    /// True whenever there IS somewhere for the knowledge to go. Only then do the switches mean anything.
    var sharing:Bool { kind != .off }
    static let off=TeamTarget(kind:.off,line:TeamInvite.offLine)
}

/// What a join attempt came back with, phrased for the confirmation sheet. Identifiable so it can BE the sheet.
struct TeamJoinOutcome:Identifiable, Equatable {
    let id=UUID()
    let ok:Bool
    let line:String
}

enum TeamInvite {
    static let scheme="meetingos"
    static let host="join"
    static let fileExtension="meetingos-invite"
    /// What the save panel offers. The extension is declared in the Info.plist (UTI local.boran.meeting-os.invite),
    /// so a double click on the saved file opens Meeting OS rather than a text editor.
    static let fileName="Meeting OS Daveti."+fileExtension
    static let uti="local.boran.meeting-os.invite"
    static let offLine="Kapalı (bulut bağlı değil: OpenRouter anahtarı girilince kendiliğinden bağlanır)"

    // MARK: - Incoming
    /// `meetingos://join?…`. The transcript's own `meetingos://word` links are NOT this and must never be
    /// mistaken for it: the host is what separates them.
    static func isJoinURL(_ url:URL)->Bool {
        url.scheme?.lowercased()==scheme && url.host?.lowercased()==host
    }
    static func isInviteFile(_ url:URL)->Bool {
        url.isFileURL && url.pathExtension.lowercased()==fileExtension
    }
    /// What a paste field should send on, or nil when there is nothing to send. Deliberately forgiving: the
    /// bridge accepts a link, the JSON of an invite file and a bare token, so the field asks for none of them
    /// by name.
    static func payload(_ raw:String)->String? {
        let text=raw.trimmingCharacters(in:.whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }

    // MARK: - Effective target
    /// The bridge's `setup_status` answer, read as one line. `home` abbreviates a folder path to `~`; pass ""
    /// to leave it verbatim (a test does, so the line is not tied to whoever runs it).
    static func target(_ r:[String:Any],home:String="")->TeamTarget {
        let kind=r["team_root_kind"] as? String ?? "none"
        switch kind {
        case "cloud":
            let cloud=r["team_cloud"] as? [String:Any] ?? [:]
            let id=cloud["team_id_short"] as? String ?? ""
            // The index lists the hosts the server knows; before the first sync it knows none, and this Mac is
            // still one Mac.
            let macs=max((cloud["hosts"] as? [Any])?.count ?? 0,1)
            let lastOK=cloud["last_ok"] as? String ?? ""
            var line="Ekip bulutu · "+(id.isEmpty ? "—" : id)+" · \(macs) Mac"
            line += lastOK.isEmpty ? " · ilk eşitleme bekleniyor" : " · son eşitleme "+SetupStatus.syncClock(lastOK)
            return TeamTarget(kind:.cloud,line:line)
        case "team","icloud":
            // iCloud Drive is a folder like any other here: it is where the files go, so the switches that stop
            // them going there have to work. It is only ever the answer when no key and no token exist.
            let root=r["team_root"] as? String ?? ""
            let shown=home.isEmpty || root.isEmpty ? root : root.replacingOccurrences(of:home,with:"~")
            return TeamTarget(kind:.folder,line:"Ekip klasörü · "+(shown.isEmpty ? "seçildi" : shown)+(kind=="icloud" ? " (iCloud Drive)" : ""))
        default: return .off
        }
    }

    // MARK: - Outcome
    /// `team_join`'s answer as the sheet says it. An error is shown verbatim — the Python side writes those in
    /// Turkish, one short sentence, and re-wording them here would only ever lose the reason.
    static func outcome(_ r:[String:Any])->TeamJoinOutcome {
        if let error=r["error"] as? String, !error.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty {
            return TeamJoinOutcome(ok:false,line:error)
        }
        guard r["joined"] as? Bool == true else { return TeamJoinOutcome(ok:false,line:"Davet uygulanamadı") }
        let id=r["team_id_short"] as? String ?? ""
        let hosts=((r["synced"] as? [String:Any])?["hosts"] as? [Any])?.count ?? 0
        var line="Ekibe katıldınız · ekip "+(id.isEmpty ? "—" : id)+" · \(max(hosts,1)) Mac"
        if r["key_written"] as? Bool == true { line += " · OpenRouter anahtarı da geldi" }
        return TeamJoinOutcome(ok:true,line:line)
    }
}
