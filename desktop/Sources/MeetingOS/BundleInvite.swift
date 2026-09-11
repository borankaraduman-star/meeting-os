import Foundation

/// The invite that ships INSIDE a downloaded bundle (`Resources/invite.json`, written by
/// `scripts/build-bundle.sh --invite`). A teammate who drags the app to Uygulamalar has no link to paste and
/// no OpenRouter key to type: the first launch reads the file and hands it to the very same `team_join`
/// bridge action a pasted link goes through, so the app and the CLI can never disagree about what a valid
/// invite is (`meeting_os/team_cloud.py` owns that).
enum BundleInvite {
    static let fileName="invite.json"
    /// UserDefaults flag: once the shipped invite has been applied it is never read again. A Mac that later
    /// LEAVES the team must not be dragged back into it by the next relaunch.
    static let importedKey="bundleInviteImported"

    /// The whole decision, with nothing to mock. Every condition has to hold: only a bundle carries an
    /// invite; a Mac that already has a key or a team has nothing to join; and it happens exactly once.
    /// `hasKey` is the setup answer's `api_key` (or the Keychain copy the app has not filed yet) and
    /// `hasTeam` is a `team_root_kind` that is not "none".
    static func shouldImportInvite(bundled:Bool,hasKey:Bool,hasTeam:Bool,alreadyImported:Bool)->Bool {
        bundled && !hasKey && !hasTeam && !alreadyImported
    }
    static func url(resources:URL?)->URL? { resources?.appendingPathComponent(fileName) }
    /// The file's text, or nil when this build shipped without `--invite`. Whitespace-only counts as nil: an
    /// empty file must send the user to the paste field, not to a join that cannot work.
    static func text(resources:URL?)->String? {
        guard let url=url(resources:resources), let text=try? String(contentsOf:url,encoding:.utf8),
              !text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }
    static func exists(resources:URL?)->Bool { text(resources:resources) != nil }
}
