import Foundation

/// The analysis model the app starts with. 1.2.69 moved the default to DeepSeek V3.2 on a fictional-case benchmark;
/// 1.2.71 moved it back after the real 41-minute meeting (DeepSeek: 100 s a chunk, then two failures; gpt-4.1-mini:
/// 214 s, done). A stored value equal to the retired 1.2.69 default never was a choice — it is cleared once; a Mac
/// that picked anything else keeps its choice.
enum AnalysisModelDefault {
    static let model="openai/gpt-4.1-mini"
    static let legacy="deepseek/deepseek-v3.2"
    static let key="cloudAnalysisModel"
    static let migratedKey="cloudAnalysisModelMoved1271"
    static func current(defaults:UserDefaults = .standard)->String {
        resolve(stored:defaults.string(forKey:key),migrated:defaults.bool(forKey:migratedKey)) { value in
            if let value { defaults.set(value,forKey:key) } else { defaults.removeObject(forKey:key) }
            defaults.set(true,forKey:migratedKey)
        }
    }
    /// Pure rule: (stored value, already migrated) → the model to use; `write` is called once when the stored value moves.
    static func resolve(stored:String?,migrated:Bool,write:(String?)->Void)->String {
        if !migrated {
            if stored==legacy { write(nil); return model }   // the old default, never a choice
            write(stored)
        }
        return stored ?? model
    }
}
