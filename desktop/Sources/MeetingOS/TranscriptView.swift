import SwiftUI

struct TranscriptView:View {
    @ObservedObject var model:Model
    var body:some View {
        ScrollView {
            // Plain VStack: LazyVStack's height estimation oscillated with long wrapped paragraphs and
            // pinned the main thread at 100% CPU after scrolling or renaming a speaker. Meetings have
            // at most a few hundred rows, so eager layout is cheap and deterministic.
            VStack(alignment:.leading,spacing:20) {
                if CloudTranscription.hiddenEchoCount(model.rows)>0 {
                    HStack(spacing:8) {
                        Image(systemName:"speaker.wave.2").foregroundStyle(.secondary)
                        Text(model.showEchoRows ? "Mikrofon yankısı bölümleri gösteriliyor · hoparlörden mikrofona düşen aynı konuşma, ayrı kişi değil" : "\(CloudTranscription.hiddenEchoCount(model.rows)) mikrofon yankısı bölümü gizlendi · hoparlörden mikrofona düşen aynı konuşma").font(.caption).foregroundStyle(.secondary)
                        Spacer()
                        Button(model.showEchoRows ? "Gizle" : "Göster") { model.showEchoRows.toggle() }.font(.caption).accessibilityIdentifier("toggleEchoRows")
                    }
                }
                if let notice=TranscriptBlocks.meetingNotice(model.rows) {
                    HStack(spacing:8) {
                        Image(systemName:"info.circle").foregroundStyle(.secondary).help(notice)
                        Text("Bulut transkript · OpenRouter").font(.caption).foregroundStyle(.secondary).help(notice)
                        if model.readingMode { Toggle("Dolgu seslerini gizle",isOn:$model.hideFillers).toggleStyle(.checkbox).font(.caption).foregroundStyle(.secondary).help("eee, ııı, yarım kelimeler yalnız okuma görünümünde gizlenir; kayıt ve arama ham metni kullanır").accessibilityIdentifier("toggleFillers") }
                        Spacer()
                        Picker("Görünüm",selection:$model.readingMode) { Text("Okuma").tag(true);Text("Bölümler").tag(false) }.pickerStyle(.segmented).labelsHidden().frame(width:170).accessibilityIdentifier("transcriptViewMode")
                    }
                }
                let canPlay = !model.recording && model.meeting?.metadata["text_only"] as? Bool != true
                let canEdit = model.meeting?.status == "complete"
                if model.readingMode && model.search.isEmpty && model.focusedSegment == nil {
                    let blocks=model.blocks
                    if TranscriptBlocks.asideCount(blocks)>0 {
                        HStack(spacing:8) {
                            Image(systemName:"text.bubble").foregroundStyle(.secondary)
                            Text(model.showAsides ? "Kısa onaylar paragraf altında gösteriliyor" : "\(TranscriptBlocks.asideCount(blocks)) kısa onay (“hı hı”, “tabii”) paragraflara katlandı").font(.caption).foregroundStyle(.secondary)
                            Spacer()
                            Button(model.showAsides ? "Gizle" : "Göster") { model.showAsides.toggle() }.font(.caption).accessibilityIdentifier("toggleAsides")
                        }
                    }

                    ForEach(blocks) { block in TranscriptBlockView(model:model,block:block,canPlay:canPlay,canEdit:canEdit,showAsides:model.showAsides) }
                    if blocks.isEmpty { TranscriptEmptyView(model:model).padding(32) }
                } else {
                    ForEach(model.filteredRows) { row in TranscriptRow(model:model,row:row,canPlay:canPlay,canEdit:canEdit).equatable() }
                    if model.filteredRows.isEmpty { TranscriptEmptyView(model:model).padding(32) }
                }
            }.padding(24)
        }
    }
}

struct TranscriptRow:View, Equatable {
    let model:Model
    let row:Row
    let canPlay:Bool
    let canEdit:Bool
    static func == (lhs:Self,rhs:Self)->Bool { lhs.row == rhs.row && lhs.canPlay == rhs.canPlay && lhs.canEdit == rhs.canEdit && lhs.model === rhs.model }
    var body:some View {
        HStack(alignment:.top,spacing:14) {
            if canPlay {
            Button { model.play(row) } label:{
                VStack(spacing:8) {
                    Image(systemName:"play.circle.fill").font(.title2).foregroundStyle(MeetingStyle.accent)
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
                Text(row.text).font(.system(size:15)).textSelection(.enabled).lineSpacing(6).fixedSize(horizontal:false,vertical:true)
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


struct TranscriptBlockView:View {
    let model:Model
    let block:TranscriptBlock
    let canPlay:Bool
    let canEdit:Bool
    let showAsides:Bool
    var body:some View {
        HStack(alignment:.top,spacing:14) {
            if canPlay {
                Button { model.play(block.lead) } label:{
                    VStack(spacing:8) {
                        Image(systemName:"play.circle.fill").font(.title2).foregroundStyle(MeetingStyle.accent)
                        Text(block.lead.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    }.frame(width:48)
                }.buttonStyle(.plain).help("Bu paragrafı dinle").accessibilityIdentifier("playBlock-\(block.id)")
            } else { Text(block.lead.time).font(.caption.monospacedDigit()).foregroundStyle(.secondary).frame(width:48) }
            VStack(alignment:.leading,spacing:7) {
                HStack {
                    Text(block.label).font(.headline).lineLimit(1)
                    if !block.lead.suggested.isEmpty && block.lead.name.isEmpty {
                        Button("Onayla") { Task { await model.confirmSuggestion(block.lead) } }.controlSize(.small).disabled(!canEdit).help("Ses profiline benziyor; tek tıkla adı onaylayın").accessibilityIdentifier("confirmSuggestion-\(block.id)")
                    }
                    Spacer(minLength:12)
                    if block.rows.count>1 { Text("\(block.rows.count) bölüm").font(.caption2).foregroundStyle(.secondary) }
                    Button("Düzelt") { model.editRow=block.lead;model.editName=block.lead.name;model.editText=block.lead.text;model.clean=false }.disabled(!canEdit).accessibilityIdentifier("editBlock-\(block.id)")
                }
                Text(model.hideFillers ? Fillers.clean(block.text) : block.text).font(.system(size:15)).textSelection(.enabled).lineSpacing(6).fixedSize(horizontal:false,vertical:true)
                let notices=Set(block.rows.map(\.notices)).filter { !$0.isEmpty }.sorted().joined(separator:" · ")
                if !notices.isEmpty { Label(notices,systemImage:"exclamationmark.triangle").font(.caption2).foregroundStyle(.orange).fixedSize(horizontal:false,vertical:true) }
                let marks=Markers.inBlock(Markers.parse(model.meeting?.metadata ?? [:]),start:block.start,end:block.end)
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
        }.padding(20).meetingCard()
    }
}
