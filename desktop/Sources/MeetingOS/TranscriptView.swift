import SwiftUI
import AppKit

struct TranscriptView:View {
    @ObservedObject var model:Model
    var body:some View {
        ScrollViewReader { proxy in ScrollView {
            // LazyVStack: a day-long meeting is 1200+ rows and an eager stack laid out every one of them on
            // open, on every rename and on every poll that published a row. The oscillation the eager stack was
            // put here to avoid came from unpinned wrapped-text heights, not from laziness — every paragraph and
            // every row keeps fixedSize(horizontal:false,vertical:true) on its text, and no row contains a
            // GeometryReader, so each item's height is a pure function of its own content and estimates converge.
            // Both ForEach bodies carry stable ids (block.id / row.id are segment ids, not offsets), which is also
            // what keeps the reveal path working: scrollTo(anchor) below resolves an id the lazy stack has not
            // built yet, because ScrollViewReader matches ids rather than materialised views.
            LazyVStack(alignment:.leading,spacing:(model.readingMode && model.search.isEmpty) ? 2 : 20) {
                let hiddenEcho=CloudTranscription.hiddenEchoCount(model.rows)
                let marks=Markers.parse(model.meeting?.metadata ?? [:])   // once per body, not once per paragraph
                NamesCard(model:model).padding(.bottom,10)
                if hiddenEcho>0 {
                    HStack(spacing:8) {
                        Image(systemName:"speaker.wave.2").foregroundStyle(.secondary)
                        Text(model.showEchoRows ? "Mikrofon yankısı bölümleri gösteriliyor · hoparlörden mikrofona düşen aynı konuşma, ayrı kişi değil" : "\(hiddenEcho) mikrofon yankısı bölümü gizlendi · hoparlörden mikrofona düşen aynı konuşma").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button(model.showEchoRows ? "Gizle" : "Göster") { model.showEchoRows.toggle() }.font(.caption).accessibilityIdentifier("toggleEchoRows")
                    }
                }
                if let notice=TranscriptBlocks.meetingNotice(model.rows) {
                    HStack(spacing:8) {
                        Image(systemName:"info.circle").foregroundStyle(.secondary).help(notice)
                        if model.readingMode && model.search.isEmpty, TranscriptBlocks.asideCount(model.blocks)>0 {
                            Button(model.showAsides ? "\(TranscriptBlocks.asideCount(model.blocks)) kısa onay gösteriliyor" : "\(TranscriptBlocks.asideCount(model.blocks)) kısa onay katlandı") { model.showAsides.toggle() }.buttonStyle(.plain).font(.caption).foregroundStyle(.secondary).help("“hı hı”, “tabii” gibi kısa onaylar paragraf altında gösterilir veya katlanır").accessibilityIdentifier("toggleAsides")
                        } else { Text("Bulut transkript").font(.caption).foregroundStyle(.secondary).help(notice) }
                        if model.readingMode { Toggle("Dolgu seslerini gizle",isOn:$model.hideFillers).toggleStyle(.checkbox).font(.caption).foregroundStyle(.secondary).help("eee, ııı, yarım kelimeler yalnız okuma görünümünde gizlenir; kayıt ve arama ham metni kullanır").accessibilityIdentifier("toggleFillers") }
                        Spacer()
                        Picker("Görünüm",selection:$model.readingMode) { Text("Okuma").tag(true);Text("Bölümler").tag(false) }.pickerStyle(.segmented).labelsHidden().frame(width:170).accessibilityIdentifier("transcriptViewMode")
                    }
                }
                let canPlay = !model.recording && model.meeting?.metadata["text_only"] as? Bool != true
                let canEdit = model.meeting?.status == "complete"
                if canEdit && !model.rows.isEmpty {
                    Text("Bir kelimeye tıklayın: yalnız burada ya da öğreterek düzeltin").font(.caption).foregroundStyle(.secondary)
                }
                if model.readingMode && model.search.isEmpty && model.focusedSegment == nil {
                    let blocks=model.blocks

                    ForEach(Array(blocks.enumerated()),id:\.element.id) { i,block in
                        if i>0, blocks[i-1].label != block.label { Divider().padding(.leading,62).padding(.vertical,4) }
                        TranscriptBlockView(model:model,block:block,canPlay:canPlay,canEdit:canEdit,showAsides:model.showAsides,highlighted:model.highlighted.map { h in block.rows.contains { $0.id==h } || block.asides.contains { $0.id==h } } ?? false,continued:i>0 && blocks[i-1].label==block.label,marks:Markers.inBlock(marks,start:block.start,end:block.end),hideFillers:model.hideFillers,profiles:model.profiles.map(\.name),attendees:model.calendarAttendees,wordFix:model.wordFix?.blockID==block.id ? model.wordFix : nil).equatable().id(block.id)
                    }
                    if blocks.isEmpty { TranscriptEmptyView(model:model).padding(32) }
                } else {
                    let rows=model.visibleRows   // filtered once per rebuild, not once per body pass
                    ForEach(rows) { row in TranscriptRow(model:model,row:row,canPlay:canPlay,canEdit:canEdit,wordFix:model.wordFix?.blockID==row.id ? model.wordFix : nil).equatable().id(row.id) }
                    if rows.isEmpty { TranscriptEmptyView(model:model).padding(32) }
                }
            }.padding(24)
        }
        // Every word in the transcript is a link to a private meetingos://word URL; this is where a click
        // on one lands. Nothing else in the app opens URLs from inside the transcript, so the handler can own
        // the scheme outright and hand everything else back to the system.
        .environment(\.openURL,OpenURLAction { url in
            guard let ref=WordClick.parse(url) else { return .systemAction }
            guard model.meeting?.status=="complete", !model.recording else { return .handled }
            let anchor=(model.readingMode && model.search.isEmpty && model.focusedSegment==nil) ? (model.blockId(containing:ref.segment) ?? ref.segment) : ref.segment
            model.wordFix=WordFix(segmentID:ref.segment,index:ref.index,original:ref.word,blockID:anchor)
            return .handled
        })
        .onChange(of:model.revealToken) { _,_ in
            guard let target=model.revealTarget else { return }
            let anchor=(model.readingMode && model.search.isEmpty) ? (model.blockId(containing:target) ?? target) : target
            withAnimation(.easeInOut(duration:0.35)) { proxy.scrollTo(anchor,anchor:.center) }
        } }
    }
}

struct TranscriptRow:View, Equatable {
    let model:Model
    let row:Row
    let canPlay:Bool
    let canEdit:Bool
    var wordFix:WordFix?   // non-nil only for the row whose word was clicked, so no other row redraws
    static func == (lhs:Self,rhs:Self)->Bool { lhs.row == rhs.row && lhs.canPlay == rhs.canPlay && lhs.canEdit == rhs.canEdit && lhs.wordFix == rhs.wordFix && lhs.model === rhs.model }
    var body:some View {
        HStack(alignment:.top,spacing:14) {
            if canPlay {
            Button { model.play(row) } label:{
                VStack(spacing:8) {
                    PlayGlyph(playback:model.playback,key:"row:\(row.id)",idle:"play.circle.fill",font:.title2)
                    Text(row.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                }.frame(width:48)
            }
            .buttonStyle(.plain).help("Bu bölümü dinle")
            .disabled(!canPlay)
            .accessibilityIdentifier("playSegment-\(row.id)")
            .accessibilityLabel("Bu bölümü dinle, \(row.time)")
            } else if !row.time.isEmpty {
                Text(row.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width:48)
            }
            VStack(alignment:.leading,spacing:7) {
                VStack(alignment:.leading,spacing:4) {
                    HStack { Text(row.label).font(.headline).lineLimit(1); Spacer(minLength:12); editButton }
                    Text(row.flags.contains("possible_echo") ? "Mikrofon · sistem sesinin yankısı, özet ve görevlerde yok sayılır" : (row.source=="mic" ? "Mikrofon" : (row.source=="system" ? "Sistem sesi" : "Aktarılan metin"))).font(.caption).foregroundStyle(.secondary)
                }
                // fixedSize(vertical) pins wrapped-text heights so LazyVStack estimates converge; without it long
                // paragraphs made the layout engine oscillate and the app spun at 100% CPU.
                Text(canEdit ? WordTextCache.text(block:row.id,rows:[row],hideFillers:false) : AttributedString(row.text))
                    .font(.system(size:15)).tint(.primary).textSelection(.enabled).lineSpacing(6).fixedSize(horizontal:false,vertical:true)
                    .popover(item:Binding(get:{ wordFix },set:{ model.wordFix=$0 }),arrowEdge:.bottom) { fix in WordFixPopover(model:model,fix:fix) }
                if !row.notices.isEmpty { Label(row.notices,systemImage:"exclamationmark.triangle").font(.caption2).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true) }
            }.frame(maxWidth:.infinity,alignment:.leading)
        }.padding(20).meetingCard()
    }
    var editButton:some View {
        Button("Düzelt") { model.editRow=row;model.editName=row.name;model.editText=row.text;model.clean=false }
            .disabled(!canEdit)
            .accessibilityIdentifier("editSegment-\(row.id)")
            .accessibilityLabel("Bölümü düzelt: \(row.label)")
    }
}


struct TranscriptBlockView:View, Equatable {
    let model:Model
    let block:TranscriptBlock
    let canPlay:Bool
    let canEdit:Bool
    let showAsides:Bool
    var highlighted:Bool=false
    var continued:Bool=false   // same speaker as the previous paragraph: no repeated name header
    var marks:[Marker]=[]
    var hideFillers:Bool=true
    var profiles:[String]=[]
    var attendees:[String]=[]
    var wordFix:WordFix?   // non-nil only for the paragraph whose word was clicked

    /// Everything the body reads is a parameter, so an unrelated publish on Model leaves the paragraph untouched.
    static func ==(a:TranscriptBlockView,b:TranscriptBlockView)->Bool {
        a.model===b.model && a.block==b.block && a.canPlay==b.canPlay && a.canEdit==b.canEdit && a.showAsides==b.showAsides && a.highlighted==b.highlighted && a.continued==b.continued && a.marks==b.marks && a.hideFillers==b.hideFillers && a.profiles==b.profiles && a.attendees==b.attendees && a.wordFix==b.wordFix
    }
    /// Rename this speaker's whole cluster from the paragraph header: saved profiles, calendar attendees, or the full editor.
    var speakerMenu:some View {
        Menu {
            let known=NameFold.unique(profiles.sorted())
            if !known.isEmpty { Section("Ses profilleri") { ForEach(known,id:\.self) { n in Button(n) { Task { await model.nameSpeaker(block.lead.speaker,n) } } } } }
            if !attendees.isEmpty { Section("Takvim katılımcıları") { ForEach(attendees,id:\.self) { n in Button(n) { Task { await model.nameSpeaker(block.lead.speaker,n) } } } } }
            Button("Yeni isim…") { model.editRow=block.lead;model.editName=block.lead.name;model.editText=block.lead.text;model.clean=false }
        } label: { HStack(spacing:4) { Text(block.label).font(.headline).lineLimit(1); Image(systemName:"chevron.down").font(.caption2).foregroundStyle(.secondary) } }
        .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize().help("Bu konuşmacının bütün paragraflarını adlandır").accessibilityIdentifier("speakerMenu-\(block.id)")
    }
    var body:some View {
        HStack(alignment:.top,spacing:14) {
            if canPlay {
                Button { model.play(block.lead) } label:{
                    HStack(spacing:4) {
                        PlayGlyph(playback:model.playback,key:"row:\(block.lead.id)",idle:"play.fill",font:.caption2)
                        Text(block.lead.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }.frame(width:48,alignment:.leading)
                }.buttonStyle(.plain).help("Bu paragrafı dinle").accessibilityIdentifier("playBlock-\(block.id)").padding(.top,continued ? 2 : 3)
            } else { Text(block.lead.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width:48,alignment:.leading) }
            VStack(alignment:.leading,spacing:5) {
                if !continued { HStack {
                    if canEdit && block.lead.source != "mic" && block.lead.flags.contains("cloud_diarization") { speakerMenu } else { Text(block.label).font(.headline).lineLimit(1) }
                    if !block.lead.suggested.isEmpty && block.lead.name.isEmpty {
                        Button("Onayla") { Task { await model.confirmSuggestion(block.lead) } }.controlSize(.small).disabled(!canEdit).help("Ses profiline benziyor; tek tıkla adı onaylayın").accessibilityIdentifier("confirmSuggestion-\(block.id)")
                    }
                    Spacer(minLength:12)
                    if block.rows.count>1 { Text("\(block.rows.count) bölüm").font(.caption2).foregroundStyle(.secondary) }
                    Button("Düzelt") { model.editRow=block.lead;model.editName=block.lead.name;model.editText=block.lead.text;model.clean=false }.disabled(!canEdit).controlSize(.small).accessibilityIdentifier("editBlock-\(block.id)")
                } }
                HStack(alignment:.top,spacing:8) {
                    // Every word is its own link (WordClick); the cached AttributedString keeps a 1200-row
                    // meeting as cheap as the plain string it replaced.
                    Text(canEdit ? WordTextCache.text(block:block.id,rows:block.rows,hideFillers:hideFillers) : AttributedString(hideFillers ? Fillers.clean(block.text) : block.text))
                        .font(.system(size:15)).tint(.primary).textSelection(.enabled).lineSpacing(6).fixedSize(horizontal:false,vertical:true).frame(maxWidth:760,alignment:.leading)
                        .popover(item:Binding(get:{ wordFix },set:{ model.wordFix=$0 }),arrowEdge:.bottom) { fix in WordFixPopover(model:model,fix:fix) }
                        .pointerStyle(canEdit ? .link : .default)
                    if continued { Spacer(minLength:0); Button("Düzelt") { model.editRow=block.lead;model.editName=block.lead.name;model.editText=block.lead.text;model.clean=false }.disabled(!canEdit).controlSize(.mini).buttonStyle(.plain).foregroundStyle(.secondary).accessibilityIdentifier("editBlock-\(block.id)") }
                }
                let notices=Set(block.rows.map(\.notices)).filter { !$0.isEmpty }.sorted().joined(separator:" · ")
                if !notices.isEmpty { Label(notices,systemImage:"exclamationmark.triangle").font(.caption2).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true) }
                if !marks.isEmpty {
                    HStack(spacing:6) { ForEach(marks) { m in Label("\(m.label) · \(m.time)",systemImage:"bookmark.fill").font(.caption).foregroundStyle(MeetingStyle.accent).padding(.horizontal,8).padding(.vertical,4).background(MeetingStyle.accent.opacity(0.12),in:Capsule()) } }
                }
                if showAsides && !block.asides.isEmpty {
                    HStack(spacing:6) {
                        ForEach(block.asides) { aside in
                            Text("\(aside.label): \(aside.text)").font(.caption).padding(.horizontal,8).padding(.vertical,4).background(Color.secondary.opacity(0.12),in:Capsule()).help(aside.time)
                        }
                    }.fixedSize(horizontal:false,vertical:true)
                }
            }.frame(maxWidth:.infinity,alignment:.leading)
        }.padding(.vertical,continued ? 4 : 10).padding(.horizontal,12).background(MeetingStyle.accent.opacity(highlighted ? 0.10 : 0),in:RoundedRectangle(cornerRadius:10)).overlay(RoundedRectangle(cornerRadius:10).stroke(MeetingStyle.accent.opacity(highlighted ? 0.9 : 0),lineWidth:2)).animation(.easeOut(duration:0.4),value:highlighted)
    }
}
