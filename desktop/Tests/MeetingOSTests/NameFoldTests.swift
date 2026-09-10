import XCTest
@testable import MeetingOS

/// The Swift side of a name comparison has to reach the same verdict as `store.fold_name` / `memory.owner_key`
/// on the Python side. When it does not, "Bana ait" hides the tasks the bridge filed under the same person and
/// the calendar offers "Ayşe" next to "Ayse" as if they were two people.
final class NameFoldTests:XCTestCase {
    func testTurkishDottedAndDotlessIAreOnePerson() {
        XCTAssertTrue(NameFold.same("İlker","Ilker"))
        XCTAssertTrue(NameFold.same("İlker","ilker"))
        XCTAssertTrue(NameFold.same("ILKER","ılker"))
        XCTAssertTrue(NameFold.same("İLKER","İlker"))
    }
    func testDiacriticsDoNotSeparatePeople() {
        XCTAssertTrue(NameFold.same("Ayşe","Ayse"))
        XCTAssertTrue(NameFold.same("AYŞE","ayşe"))
        XCTAssertTrue(NameFold.same("Gökçe","Gokce"))
        XCTAssertTrue(NameFold.same("Çağrı","Cagri"))
        XCTAssertTrue(NameFold.same("Şüküfe","Sukufe"))
    }
    func testDifferentPeopleStayDifferent() {
        XCTAssertFalse(NameFold.same("Ayşe","Ahmet"))
        XCTAssertFalse(NameFold.same("Ali","Ali Tasarım"))
        XCTAssertFalse(NameFold.same("Mehmet","Mehmed"))
    }
    /// An unset name is not a person: an empty "Adınız" must match nobody, or every ownerless task would
    /// land in "Bana ait" the moment the field is blank.
    func testEmptyNameMatchesNobody() {
        XCTAssertFalse(NameFold.same("",""))
        XCTAssertFalse(NameFold.same("   ",""))
        XCTAssertFalse(NameFold.same(nil,"Ayşe"))
        XCTAssertFalse(NameFold.same("Ayşe",nil))
        XCTAssertTrue(NameFold.key("").isEmpty)
        XCTAssertTrue(NameFold.key(nil).isEmpty)
    }
    func testSurroundingSpaceIsNotAPerson() {
        XCTAssertTrue(NameFold.same("  Ayşe  ","Ayşe"))
        XCTAssertEqual(NameFold.key(" Ali "),NameFold.key("ali"))
    }
    func testKeyIsLowercasedAscii() {
        XCTAssertEqual(NameFold.key("Ali"),"ali")
        XCTAssertEqual(NameFold.key("AYSE"),"ayse")
        XCTAssertEqual(NameFold.key("Ayşe"),"ayse")
        XCTAssertEqual(NameFold.key("Işık"),"isik")
        XCTAssertEqual(NameFold.key("İnci"),"inci")
    }
    /// The name pickers show what the user typed; the fold only decides which spellings are the same entry.
    func testUniqueKeepsTheFirstSpelling() {
        XCTAssertEqual(NameFold.unique(["Ayşe","Ayse","AYŞE","Ahmet"]),["Ayşe","Ahmet"])
        XCTAssertEqual(NameFold.unique(["Ilker","İlker"]),["Ilker"])
        XCTAssertEqual(NameFold.unique(["","  ","Ali"]),["Ali"])
        XCTAssertEqual(NameFold.unique([]),[])
    }
}
