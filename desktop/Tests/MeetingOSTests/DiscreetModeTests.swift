import XCTest
import AppKit
@testable import MeetingOS

/// Göze batma: the pure decisions behind "nobody in the meeting should be able to tell this is recording".
/// The menu bar label, the floating panel's right to be on screen, window capture privacy and the notification
/// gate are all value-in/value-out, so they can be pinned down without a window server or a real recording.
final class DiscreetModeTests:XCTestCase {

    // MARK: menu bar

    func testIdleLabelIsUnchangedInBothModes() {
        for discreet in [true,false] {
            let quiet=DiscreetMode.menuBar(recording:false,discreet:discreet,zoomOpen:false,elapsed:"04:12")
            XCTAssertEqual(quiet,DiscreetMode.MenuBarLook(glyph:"waveform",text:nil))
            let zoom=DiscreetMode.menuBar(recording:false,discreet:discreet,zoomOpen:true,elapsed:"04:12")
            XCTAssertEqual(zoom,DiscreetMode.MenuBarLook(glyph:"video.badge.waveform",text:nil))
        }
    }

    /// The whole point: with discreet mode on, starting a recording changes nothing in the menu bar.
    func testRecordingIsIndistinguishableFromIdleWhenDiscreet() {
        for zoomOpen in [true,false] {
            let idle=DiscreetMode.menuBar(recording:false,discreet:true,zoomOpen:zoomOpen,elapsed:"00:00")
            let live=DiscreetMode.menuBar(recording:true,discreet:true,zoomOpen:zoomOpen,elapsed:"12:34")
            XCTAssertEqual(live,idle)
        }
    }

    func testDiscreetLabelCarriesNoRedDotClockOrText() {
        let live=DiscreetMode.menuBar(recording:true,discreet:true,zoomOpen:true,elapsed:"12:34")
        XCTAssertNil(live.text)                                  // no elapsed time, no "kaydediyor"
        XCTAssertFalse(live.glyph.contains("record"))            // no red record dot
        XCTAssertEqual(live.glyph,DiscreetMode.idleGlyph(zoomOpen:true))
    }

    /// Switched off, today's label comes back exactly as it was.
    func testLoudModeKeepsTheRecordDotAndElapsedTime() {
        let live=DiscreetMode.menuBar(recording:true,discreet:false,zoomOpen:true,elapsed:"12:34")
        XCTAssertEqual(live,DiscreetMode.MenuBarLook(glyph:"record.circle.fill",text:"12:34"))
    }

    /// The elapsed time ticks every second; a discreet label must not redraw with it.
    func testDiscreetLabelDoesNotChangeAsTheClockRuns() {
        let a=DiscreetMode.menuBar(recording:true,discreet:true,zoomOpen:false,elapsed:"00:01")
        let b=DiscreetMode.menuBar(recording:true,discreet:true,zoomOpen:false,elapsed:"59:59")
        XCTAssertEqual(a,b)
    }

    // MARK: floating panel

    /// 11 Sep 2026: the panel was photographed floating over a live Zoom call. It is gone for good.
    func testPanelNeverAppearsAtAll() {
        for recording in [true,false] { for enabled in [true,false] { for discreet in [true,false] { for sharing in [true,false] {
            XCTAssertFalse(DiscreetMode.panelVisible(recording:recording,panelEnabled:enabled,discreet:discreet,sharing:sharing))
        }}}}
    }

    func testPanelNeverAppearsWithoutARecordingOrAgainstTheUsersSetting() {
        XCTAssertFalse(DiscreetMode.panelVisible(recording:false,panelEnabled:true,discreet:true,sharing:false))
        XCTAssertFalse(DiscreetMode.panelVisible(recording:false,panelEnabled:true,discreet:false,sharing:false))
        XCTAssertFalse(DiscreetMode.panelVisible(recording:true,panelEnabled:false,discreet:true,sharing:false))
        XCTAssertFalse(DiscreetMode.panelVisible(recording:true,panelEnabled:false,discreet:false,sharing:true))
    }

    // MARK: window privacy and notifications

    func testDiscreetModeExcludesWindowsFromCaptureAndRestoresTheDefault() {
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:true),NSWindow.SharingType.none)
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:false),NSWindow.SharingType.readOnly)
        // Outside a meeting the user's own screenshots must work (11 Sep 2026); in a meeting or while sharing, hidden.
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:true,inMeeting:false,sharing:false),NSWindow.SharingType.readOnly)
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:true,inMeeting:true,sharing:false),NSWindow.SharingType.none)
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:true,inMeeting:false,sharing:true),NSWindow.SharingType.none)
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:false,inMeeting:true,sharing:true),NSWindow.SharingType.readOnly)
    }

    /// `scripts/verify-privacy.sh` writes this preference to stand in for "a Zoom meeting is on screen" — and for
    /// nothing else. Discreet mode still decides, so what the script proves on the screen is the path the user
    /// actually gets, not a back door built for the proof. The key name is part of the script's contract.
    func testThePrivacyProbeOnlyStandsInForAMeetingOnScreen() {
        XCTAssertEqual(DiscreetMode.probeKey,"privacyProbe")
        let probing=true
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:true,inMeeting:false || probing,sharing:false),NSWindow.SharingType.none)
        XCTAssertEqual(DiscreetMode.windowSharingType(discreet:false,inMeeting:false || probing,sharing:false),NSWindow.SharingType.readOnly)
    }

    func testNothingIsDeliveredWhileRecordingInAMeetingOrSharing() {
        XCTAssertTrue(DiscreetMode.mayNotify(recording:false,meetingOpen:false,sharing:false))
        XCTAssertFalse(DiscreetMode.mayNotify(recording:true,meetingOpen:false,sharing:false))
        XCTAssertFalse(DiscreetMode.mayNotify(recording:false,meetingOpen:true,sharing:false))
        XCTAssertFalse(DiscreetMode.mayNotify(recording:false,meetingOpen:false,sharing:true))   // sharing without Zoom counts too
    }

    // MARK: sharing detection

    func zoom(_ name:String,layer:Int=0)->[String:Any] { ["kCGWindowOwnerName":"zoom.us","kCGWindowName":name,"kCGWindowLayer":layer] }
    var running:Set<String> { ["us.zoom.xos"] }

    func testShareToolbarAndShareStripAreReadAsSharing() {
        for name in ["zoom share toolbar window","Zoom Share Statusbar Window","You are screen sharing","Ekran paylaşımınız duruyor","Ekran Paylaş"] {
            XCTAssertTrue(ZoomWatch.classify(zoom(name)).sharing,name)
            XCTAssertTrue(ZoomWatch.classify(zoom(name)).meeting,name)   // sharing implies a live meeting
        }
    }

    func testOrdinaryMeetingAndHomeWindowsAreNotSharing() {
        XCTAssertFalse(ZoomWatch.classify(zoom("Zoom Meeting")).sharing)
        XCTAssertFalse(ZoomWatch.classify(zoom("Zoom Workplace")).sharing)
        XCTAssertFalse(ZoomWatch.classify(["kCGWindowOwnerName":"Safari","kCGWindowName":"You are screen sharing"]).sharing)
    }

    /// The share strip can sit anywhere in the list; the walk must not stop at the first meeting window.
    func testSharingIsFoundBehindAMeetingWindow() {
        let windows=[zoom("Zoom Meeting"),["kCGWindowOwnerName":"Finder","kCGWindowName":"Masaüstü"],zoom("zoom share toolbar window")]
        let f=ZoomWatch.flags(windows:windows,runningBundles:running)
        XCTAssertTrue(f.sharing); XCTAssertTrue(f.strict); XCTAssertTrue(f.open)
    }

    func testFlagsKeepTheirOldMeaning() {
        let meeting=ZoomWatch.flags(windows:[zoom("Zoom Meeting")],runningBundles:running)
        XCTAssertEqual(meeting.open,true); XCTAssertEqual(meeting.strict,true); XCTAssertFalse(meeting.sharing)
        let home=ZoomWatch.flags(windows:[zoom("Zoom Workplace")],runningBundles:running)
        XCTAssertEqual(home.open,true); XCTAssertEqual(home.strict,false); XCTAssertFalse(home.sharing)
        let away=ZoomWatch.flags(windows:[zoom("zoom share toolbar window")],runningBundles:["com.apple.Safari"])
        XCTAssertFalse(away.open); XCTAssertFalse(away.strict); XCTAssertFalse(away.sharing)   // Zoom is not running
    }

    /// End to end on values: sharing starts, the panel goes; sharing ends, it comes back — and through all of it
    /// the menu bar never moves.
    func testShareStartsAndEndsAroundALiveRecording() {
        let before=ZoomWatch.flags(windows:[zoom("Zoom Meeting")],runningBundles:running)
        let during=ZoomWatch.flags(windows:[zoom("Zoom Meeting"),zoom("You are screen sharing")],runningBundles:running)
        XCTAssertFalse(before.sharing); XCTAssertTrue(during.sharing); XCTAssertFalse(after().sharing)   // the share window is still detected (notifications, window privacy)
        XCTAssertFalse(DiscreetMode.panelVisible(recording:true,panelEnabled:true,discreet:true,sharing:during.sharing))
        XCTAssertEqual(DiscreetMode.menuBar(recording:true,discreet:true,zoomOpen:true,elapsed:"01:00"),
                       DiscreetMode.menuBar(recording:true,discreet:true,zoomOpen:true,elapsed:"02:00"))
    }
    func after()->(open:Bool,strict:Bool,sharing:Bool) { ZoomWatch.flags(windows:[zoom("Zoom Meeting")],runningBundles:running) }
}
