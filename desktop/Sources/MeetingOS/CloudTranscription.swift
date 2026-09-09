import Foundation

/// Pure argument builders for the cloud-only transcription path. No local STT, diarization or
/// identity model is loaded anywhere on this path; the backend refuses a different model on resume.
enum CloudTranscription {
    static let modeKey="transcriptionMode"
    static let modelKey="cloudTranscriptionModel"
    static let defaultModel="microsoft/mai-transcribe-2"
    static func recordArguments(mode:String,directory:String,title:String,receipt:String)->[String] {
        var args=["record",directory,"--seconds","14400","--title",title,"--output",receipt]
        if mode != "openrouter" { args.insert("--live",at:2) }   // live local preview only in local mode
        return args
    }
    static func finalizeArguments(meeting:String,model:String?,output:String)->[String] {
        var args=["openrouter-finalize",meeting,"--allow-upload","--output",output]
        if let model, !model.isEmpty { args += ["--model",model] }
        return args
    }
    static func importArguments(path:String,title:String,model:String,output:String)->[String] {
        ["openrouter-import","--no-local","--allow-upload","--model",model,"--title",title,"--output",output,path]
    }
    /// Meetings created by the cloud-only path resume through finalize; older Sherpa-based imports keep their own resume.
    static func resumeArguments(meeting:Meeting,model:String,output:String)->[String] {
        if meeting.metadata["cloud_mode"] != nil { return finalizeArguments(meeting:meeting.id,model:nil,output:output) }
        return ["openrouter-import","--allow-upload","--model",model,"--output",output,"--resume",meeting.id]
    }
    static func canFinalize(meeting:Meeting?,busy:Bool)->Bool {
        guard let m=meeting, !busy, m.status != "complete", m.recoveryState != "active" else { return false }
        return m.metadata["capture_dir"] is String || m.metadata["cloud_mode"] != nil
    }
}
