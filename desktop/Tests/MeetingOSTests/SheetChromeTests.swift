import XCTest
@testable import MeetingOS

/// The chrome itself is a view, but what it renders is data: a title that is never blank, and a settings sheet
/// whose height leaves the pinned ✕ on screen. Both are asserted here so a later edit cannot quietly bring back
/// an untitled sheet or a sheet taller than the display.
final class SheetChromeTests:XCTestCase {
    func testEverySheetTitleIsUsableAndDistinct() {
        XCTAssertFalse(SheetChrome.titles.isEmpty)
        for t in SheetChrome.titles {
            XCTAssertTrue(SheetChrome.usable(t),"blank title: \(t)")
            XCTAssertEqual(t,t.trimmingCharacters(in:.whitespacesAndNewlines),"padded title: \(t)")
        }
        XCTAssertEqual(Set(SheetChrome.titles).count,SheetChrome.titles.count,"two sheets share a title")
    }

    func testCleanSampleTitleFallsBackWhenTheProfileHasNoName() {
        XCTAssertEqual(SheetChrome.cleanSample(name:"Ayşe"),"“Ayşe” için temiz örnek")
        XCTAssertEqual(SheetChrome.cleanSample(name:"  Ayşe  "),"“Ayşe” için temiz örnek")
        XCTAssertEqual(SheetChrome.cleanSample(name:"   "),"Temiz örnek")
        XCTAssertTrue(SheetChrome.usable(SheetChrome.cleanSample(name:"")))
    }

    func testUsableRejectsWhitespaceOnly() {
        XCTAssertFalse(SheetChrome.usable(""))
        XCTAssertFalse(SheetChrome.usable("  \n "))
        XCTAssertTrue(SheetChrome.usable("Ayarlar"))
    }

    func testCloseControlIsOneIdentifierEverywhere() {
        XCTAssertEqual(SheetChrome.closeIdentifier,"closeSheet")
        XCTAssertTrue(SheetChrome.closeHelp.contains("Esc"))
        XCTAssertTrue(SheetChrome.compactGlyph<SheetChrome.glyph)
    }

    /// The settings sheet is the tall one: the chrome is added on top of the section's content height, and the
    /// screen still wins, so the header (and its ✕) can never be pushed past the bottom of the display.
    func testSettingsSheetHeightAddsChromeAndClampsToScreen() {
        let roomy=SettingsSections.sheetHeight("genel",screen:1600)
        XCTAssertEqual(roomy,Double(SettingsSections.height("genel"))+SettingsSections.chromeHeight)
        let cramped=SettingsSections.sheetHeight("sesler",screen:800)
        XCTAssertEqual(cramped,720)                                   // 800 - 80, not the 940 the section wants
        XCTAssertLessThanOrEqual(cramped,800)
        for s in SettingsSections.all+["sozluk","depolama","bilinmeyen"] {
            XCTAssertGreaterThanOrEqual(SettingsSections.sheetHeight(s,screen:400),360)   // never a slit on a tiny display
        }
    }

    /// The old five-way section values still map somewhere, and the content heights the sheet was tuned to are
    /// unchanged by the chrome — only the window around them grew.
    func testSectionContentHeightsAreUnchanged() {
        XCTAssertEqual(SettingsSections.height("genel"),540)
        XCTAssertEqual(SettingsSections.height("sesler"),940)
        XCTAssertEqual(SettingsSections.height("sistem"),760)
    }
}
