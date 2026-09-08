import SwiftUI

struct TranscriptView:View {
    @ObservedObject var model:Model
    var body:some View {
        ScrollView {
            LazyVStack(alignment:.leading,spacing:20) {
                ForEach(model.filteredRows) { row in TranscriptRow(model:model,row:row,canPlay:!model.recording && model.meeting?.metadata["text_only"] as? Bool != true,canEdit:model.meeting?.status == "complete").equatable() }
                if model.filteredRows.isEmpty { TranscriptEmptyView(model:model).padding(32) }
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
                    Text(row.source=="mic" ? "Mikrofon" : (row.source=="system" ? "Sistem sesi" : "Aktarılan metin")).font(.caption).foregroundStyle(.secondary)
                }
                Text(row.text).font(.system(size:15)).textSelection(.enabled).lineSpacing(6)
                if !row.notices.isEmpty { Label(row.notices,systemImage:"exclamationmark.triangle").font(.caption2).foregroundStyle(.orange) }
            }
        }.padding(20).meetingCard()
    }
    var editButton:some View {
        Button("Düzelt") { model.editRow=row;model.editName=row.name;model.editText=row.text;model.clean=false }
            .disabled(!canEdit)
            .accessibilityIdentifier("editSegment-\(row.id)")
            .accessibilityLabel("Bölümü düzelt: \(row.label)")
    }
}
