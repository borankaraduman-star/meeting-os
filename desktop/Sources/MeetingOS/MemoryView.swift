import SwiftUI

struct MemoryView:View {
    @ObservedObject var m:Model
    @State private var mode="search"
    @FocusState private var queryFocused:Bool
    var memoryQueryField:some View {
        TextField(mode=="decisions" ? "Kararlarda ara" : (mode=="questions" ? "Sorularda ara" : "Örn. onboarding PRD"),text:$m.memoryQuery).onSubmit { Task { await m.runMemoryQuery(mode:mode) } }
            .focused($queryFocused).onChange(of:m.memoryFocusToken) { _,_ in queryFocused=true }
            .accessibilityIdentifier("memoryQueryField").accessibilityLabel("Hafızada ara")
    }
    var body:some View { VStack(alignment:.leading,spacing:16) {
        HStack { Label("Toplantı hafızası",systemImage:"sparkle.magnifyingglass").font(.system(size:23,weight:.bold,design:.rounded)); Spacer(); Picker("Görünüm",selection:$mode) { Text("Ara").tag("search"); Text("Kararlar").tag("decisions"); Text("Sorular").tag("questions"); Text("Beklediklerim").tag("waiting") }.pickerStyle(.segmented).frame(width:380).accessibilityIdentifier("memoryMode") }
        if mode != "waiting" {
            HStack { memoryQueryField; Button("Ara") { Task { await m.runMemoryQuery(mode:mode) } }.accessibilityIdentifier("memorySearchButton"); if mode=="search" { Button("Kayıtlardan yanıtla",action:m.askMemory).disabled(m.busy || m.memoryQuery.isEmpty).accessibilityIdentifier("memoryAskButton") } }
        }
        if mode=="decisions" { ScrollView { DecisionLogView(m:m).padding(.bottom,24) } } else if mode=="waiting" { ScrollView { WaitingView(m:m).padding(.bottom,24) } } else if mode=="questions" { ScrollView { QuestionRadarView(m:m).padding(.bottom,24) } } else {Text("Anahtar kelimelerle bütün toplantılarda arayın veya kaynaklı bir yanıt hazırlatın.").foregroundStyle(.secondary)
        ScrollView { VStack(alignment:.leading,spacing:18) { if !m.answer.isEmpty { Text(m.answer).textSelection(.enabled);EvidenceView(m:m,evidence:m.answerEvidence);Divider() };EvidenceView(m:m,evidence:m.hits) }.frame(maxWidth:.infinity,alignment:.leading) }
        }
    }.padding(24).onChange(of:mode) { _,new in Task { await m.runMemoryQuery(mode:new) } } }
}
