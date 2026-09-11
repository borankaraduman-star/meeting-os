import XCTest
@testable import MeetingOS

/// `runtime.json` is the only thing that tells the app where Python lives. In a checkout it names absolute
/// paths; in a downloaded bundle it names relative ones that have to be read against the app's own Resources
/// folder, because the user can drag the app anywhere.
final class RuntimeTests: XCTestCase {
    private func decode(_ json:String)throws->Runtime { try JSONDecoder().decode(Runtime.self,from:Data(json.utf8)) }

    /// build-desktop.sh has always written exactly two absolute keys; that file must keep working unchanged.
    func testDevelopmentRuntimeIsAbsoluteAndNotBundled() throws {
        let r=try decode(#"{"python":"/repo/.venv/bin/python","repo":"/repo"}"#)
        XCTAssertFalse(r.bundled); XCTAssertNil(r.version)
        let resolved=r.resolved(resources:URL(fileURLWithPath:"/Applications/Meeting OS.app/Contents/Resources"))
        XCTAssertEqual(resolved.python,"/repo/.venv/bin/python")
        XCTAssertEqual(resolved.repo,"/repo")
        XCTAssertTrue(resolved.childEnvironment(path:"/usr/bin").isEmpty)   // nothing to prepend without a bundle
    }
    func testBundledRuntimeResolvesAgainstResources() throws {
        let r=try decode(#"{"python":"runtime/bin/python3","repo":"repo","bundled":true,"version":"1.2.72"}"#)
        XCTAssertTrue(r.bundled); XCTAssertEqual(r.version,"1.2.72")
        let resources=URL(fileURLWithPath:"/Applications/Meeting OS.app/Contents/Resources")
        let resolved=r.resolved(resources:resources)
        XCTAssertEqual(resolved.python,"/Applications/Meeting OS.app/Contents/Resources/runtime/bin/python3")
        XCTAssertEqual(resolved.repo,"/Applications/Meeting OS.app/Contents/Resources/repo")
        XCTAssertTrue(resolved.bundled); XCTAssertEqual(resolved.version,"1.2.72")
        // Moving the app moves the runtime with it: the same JSON, a different folder.
        let moved=r.resolved(resources:URL(fileURLWithPath:"/Users/x/Downloads/Meeting OS.app/Contents/Resources"))
        XCTAssertEqual(moved.python,"/Users/x/Downloads/Meeting OS.app/Contents/Resources/runtime/bin/python3")
    }
    /// The bundled ffmpeg is only ever found through PATH: `shutil.which('ffmpeg')` is what the assembly pass
    /// calls, and the receiving Mac has no Homebrew.
    func testBundledChildrenGetTheRuntimeBinFirstOnPath() throws {
        let r=try decode(#"{"python":"runtime/bin/python3","repo":"repo","bundled":true}"#)
            .resolved(resources:URL(fileURLWithPath:"/Applications/Meeting OS.app/Contents/Resources"))
        XCTAssertEqual(r.binDirectory,"/Applications/Meeting OS.app/Contents/Resources/runtime/bin")
        XCTAssertEqual(r.childEnvironment(path:"/usr/bin:/bin")["PATH"],
                       "/Applications/Meeting OS.app/Contents/Resources/runtime/bin:/usr/bin:/bin")
        // An empty inherited PATH (a launch from LaunchServices with nothing set) must not produce ":"-only.
        XCTAssertEqual(r.childEnvironment(path:nil)["PATH"],
                       "/Applications/Meeting OS.app/Contents/Resources/runtime/bin:/usr/bin:/bin:/usr/sbin:/sbin")
    }
    /// A bundle whose runtime.json lost `bundled` is a development build: never a silent half-bundle.
    func testMissingFieldsDefaultToTheDevelopmentShape() throws {
        let r=try decode(#"{"python":"p","repo":"r"}"#)
        XCTAssertFalse(r.bundled); XCTAssertNil(r.version)
        XCTAssertEqual(r.resolved(resources:nil).python,"p")   // no Resources folder: leave the path alone
    }
}

/// The invite that ships inside a downloaded package. The decision is pure; the file read is not, so only the
/// decision is tested here.
final class BundleInviteTests: XCTestCase {
    func testShippedInviteIsAppliedOnceAndOnlyOnAVirginBundle() {
        XCTAssertTrue(BundleInvite.shouldImportInvite(bundled:true,hasKey:false,hasTeam:false,alreadyImported:false))
        XCTAssertFalse(BundleInvite.shouldImportInvite(bundled:false,hasKey:false,hasTeam:false,alreadyImported:false))  // a checkout ships no invite
        XCTAssertFalse(BundleInvite.shouldImportInvite(bundled:true,hasKey:true,hasTeam:false,alreadyImported:false))    // already paying its own way
        XCTAssertFalse(BundleInvite.shouldImportInvite(bundled:true,hasKey:false,hasTeam:true,alreadyImported:false))    // already in a team
        XCTAssertFalse(BundleInvite.shouldImportInvite(bundled:true,hasKey:false,hasTeam:false,alreadyImported:true))    // once, ever: leaving a team must stick
        XCTAssertEqual(BundleInvite.importedKey,"bundleInviteImported")
        XCTAssertEqual(BundleInvite.fileName,"invite.json")
    }
    func testInviteTextIsNilWithoutAFileAndForAnEmptyOne() throws {
        let dir=URL(fileURLWithPath:NSTemporaryDirectory()).appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:dir) }
        XCTAssertNil(BundleInvite.text(resources:dir)); XCTAssertFalse(BundleInvite.exists(resources:dir))
        XCTAssertNil(BundleInvite.text(resources:nil))
        try "   \n".write(to:dir.appendingPathComponent("invite.json"),atomically:true,encoding:.utf8)
        XCTAssertNil(BundleInvite.text(resources:dir))
        try #"{"v":1,"team":"abc"}"#.write(to:dir.appendingPathComponent("invite.json"),atomically:true,encoding:.utf8)
        XCTAssertEqual(BundleInvite.text(resources:dir),#"{"v":1,"team":"abc"}"#)
        XCTAssertTrue(BundleInvite.exists(resources:dir))
    }
}
