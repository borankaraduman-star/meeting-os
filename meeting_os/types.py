from dataclasses import dataclass, field, asdict

@dataclass
class Segment:
    start: float
    end: float
    text: str
    source: str
    speaker: str = 'unknown'
    speaker_name: str | None = None
    metrics: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    words: list[dict] = field(default_factory=list)
    embedding: list[float] | None = None
    embedding_model: str | None = None
    def __post_init__(self):
        import math
        if not math.isfinite(self.start) or not math.isfinite(self.end) or self.start < 0 or self.end <= self.start:
            raise ValueError('Invalid segment times')
    def to_dict(self): return asdict(self)
