import XCTest
@testable import MeetingOS

/// The rule that decides whether the owner's own voice is part of the meeting, and the Zoom menu reading
/// behind it. Every combination, because the failure mode is silent: a gate that guesses wrong either loses
/// the user's words or turns the corridor into a transcript.
final class MicGateTests:XCTestCase {
    func run(_ mode:String,_ zoomOpen:Bool,_ zoomMuted:Bool?,_ manual:Bool)->(on:Bool,reason:String) {
        MicGate.state(mode:mode,zoomOpen:zoomOpen,zoomMuted:zoomMuted,manualOn:manual)
    }
    func testZoomModeFollowsTheMuteStateAndTreatsUnknownAsOff() {
        XCTAssertEqual(run("zoom",true,false,false).on,true)      // Zoom’da ses açık
        XCTAssertEqual(run("zoom",true,false,false).reason,"zoom")
        XCTAssertEqual(run("zoom",true,true,false).on,false)      // sessizde: oda konuşması kayda girmez
        XCTAssertEqual(run("zoom",true,nil,false).on,false)       // menü okunamadı / izin yok
        XCTAssertEqual(run("zoom",false,nil,false).on,false)      // toplantı yok
        XCTAssertEqual(run("zoom",false,false,false).on,false)    // stale reading with no meeting open
    }
    func testManualModeIsOffUntilTheOverrideAndAlwaysIsOn() {
        XCTAssertEqual(run("manual",true,false,false).on,false)
        XCTAssertEqual(run("manual",false,nil,false).reason,"manual")
        XCTAssertEqual(run("always",false,nil,false).on,true)
        XCTAssertEqual(run("always",true,true,false).on,true)     // "her zaman" ignores Zoom entirely
        XCTAssertEqual(run("always",true,true,false).reason,"always")
    }
    func testTheOverrideWinsInEveryMode() {
        for mode in MicGate.modes {
            for open in [true,false] {
                for muted in [true,false,nil] {
                    let v=run(mode,open,muted,true)
                    XCTAssertTrue(v.on,"\(mode) \(open) \(String(describing:muted))")
                    XCTAssertEqual(v.reason,"manual")
                }
            }
        }
    }
    func testUnknownModesFallBackToFollowingZoom() {
        XCTAssertEqual(MicGate.normalize(nil),"zoom")
        XCTAssertEqual(MicGate.normalize(""),"zoom")
        XCTAssertEqual(MicGate.normalize("sesli"),"zoom")
        XCTAssertEqual(run("sesli",true,true,false).on,false)
        for mode in MicGate.modes { XCTAssertEqual(MicGate.normalize(mode),mode) }
    }
    func testStatusLineSaysWhyInOneSentence() {
        XCTAssertEqual(MicGate.statusLine(mode:"zoom",zoomOpen:true,zoomMuted:true,manualOn:false),"Mikrofon: kapalı · Zoom sessizde")
        XCTAssertEqual(MicGate.statusLine(mode:"zoom",zoomOpen:true,zoomMuted:false,manualOn:false),"Mikrofon: açık · Zoom’da ses açık")
        XCTAssertEqual(MicGate.statusLine(mode:"zoom",zoomOpen:true,zoomMuted:nil,manualOn:true),"Mikrofon: açık · elle")
        XCTAssertEqual(MicGate.statusLine(mode:"zoom",zoomOpen:true,zoomMuted:nil,manualOn:false,trusted:false),"Mikrofon: kapalı · Erişilebilirlik izni yok")
        XCTAssertEqual(MicGate.statusLine(mode:"zoom",zoomOpen:false,zoomMuted:nil,manualOn:false),"Mikrofon: kapalı · Zoom toplantısı yok")
        XCTAssertEqual(MicGate.statusLine(mode:"always",zoomOpen:false,zoomMuted:nil,manualOn:false),"Mikrofon: açık · her zaman")
        XCTAssertEqual(MicGate.statusLine(mode:"manual",zoomOpen:false,zoomMuted:nil,manualOn:false),"Mikrofon: kapalı · elle açılmadı")
        XCTAssertEqual(MicGate.overrideLabel(false),"Sesimi de kaydet  ⌃⌥V")
        XCTAssertEqual(MicGate.overrideLabel(true),"Sesimi kaydetme  ⌃⌥V")
    }
    func testJournalLineCarriesEverythingFinalizeNeeds() throws {
        let now=Date(timeIntervalSince1970:1_757_000_000)
        let line=MicGate.line(on:true,reason:"zoom",seconds:12.345,now:now)
        let d=try XCTUnwrap(try JSONSerialization.jsonObject(with:Data(line.utf8)) as? [String:Any])
        XCTAssertEqual(d["kind"] as? String,"mic_gate")
        XCTAssertEqual(d["state"] as? String,"on")
        XCTAssertEqual(d["reason"] as? String,"zoom")
        XCTAssertEqual(d["t"] as? Double,12.3)
        XCTAssertEqual(d["wall"] as? Double,1_757_000_000)
        XCTAssertEqual(MicGate.line(on:false,reason:"manual",seconds:-1,now:now).contains("\"state\":\"off\""),true)
        let zero=try XCTUnwrap(try JSONSerialization.jsonObject(with:Data(MicGate.line(on:false,reason:"manual",seconds:-1,now:now).utf8)) as? [String:Any])
        XCTAssertEqual(zero["t"] as? Double,0)   // a clock that ran backwards never writes a negative offset
    }
}

/// Zoom's own menu is the only place it says whether the local microphone is live. The walk is untestable
/// without a running meeting; the reading of the titles it brings back is not.
final class ZoomMuteTests:XCTestCase {
    func testEnglishMenuTitles() {
        XCTAssertEqual(ZoomMute.verdict(titles:["Unmute Audio","Start Video","Invite"]),true)
        XCTAssertEqual(ZoomMute.verdict(titles:["Mute Audio","Start Video","Invite"]),false)
        XCTAssertEqual(ZoomMute.verdict(titles:["unmute audio"]),true)
        XCTAssertEqual(ZoomMute.verdict(titles:["  Mute audio  "]),false)
    }
    func testTurkishMenuTitles() {
        XCTAssertEqual(ZoomMute.verdict(titles:["Sesi Aç","Videoyu Başlat"]),true)
        XCTAssertEqual(ZoomMute.verdict(titles:["Sesi Kapat","Videoyu Başlat"]),false)
    }
    func testUnmuteWinsOverItsOwnSubstringAndSilenceIsUnknown() {
        // "Unmute Audio" contains "Mute Audio": the order of the two questions is the whole test.
        XCTAssertEqual(ZoomMute.verdict(titles:["Mute Audio","Unmute Audio"]),true)
        XCTAssertNil(ZoomMute.verdict(titles:[]))
        XCTAssertNil(ZoomMute.verdict(titles:["Invite","Start Video","Katılımcılar"]))
    }
    func testMenuNamesCoverBothLocalisations() {
        XCTAssertTrue(ZoomMute.menuTitles.contains("meeting"))
        XCTAssertTrue(ZoomMute.menuTitles.contains("Toplantı".lowercased()))
    }
    /// Without the grant there is no reading at all, and the gate keeps the microphone shut in `zoom` mode.
    func testWithoutTheGrantTheReadingIsUnknown() {
        if !ZoomMute.trusted() { XCTAssertNil(ZoomMute.read()) }
        XCTAssertEqual(SetupStatus.accessibilityCheck(trusted:true,mode:"zoom").state,.ok)
        XCTAssertEqual(SetupStatus.accessibilityCheck(trusted:false,mode:"zoom").state,.optional)
        XCTAssertTrue(SetupStatus.accessibilityCheck(trusted:false,mode:"zoom").hint.contains("⌃⌥V"))
        XCTAssertTrue(SetupStatus.fixable(SetupStatus.accessibilityCheck(trusted:false,mode:"zoom")))
        XCTAssertEqual(SetupStatus.panes["accessibility"],"Privacy_Accessibility")
    }
}
