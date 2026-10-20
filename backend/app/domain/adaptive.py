"""Deterministic adaptive interview policy.

The LLM never decides *what* to assess next. This policy chooses topic, difficulty and question kind from
explicit state (the evaluation of the answer just given plus the per-topic performance profile); the Adaptive
Interview Agent only words the question within those constraints.

Evidence used per turn: the rubric band of the last answer (rubric.STRONG_THRESHOLD / WEAK_THRESHOLD), its
criterion scores (technical correctness, completeness, depth), the evaluator's confidence, and the concepts it
found missing. The few cut-offs this needs live in `AdaptiveConfig` and are set from the environment
(ADAPTIVE_* settings); each one is documented there.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

DIFFICULTIES = ("easy", "medium", "hard")

WEAK_STREAK_TO_MARK = 2
STRONG_STREAK_TO_MARK = 2


@dataclass
class PlanItem:
    topic: str
    skill: str | None
    category: str  # technical | behavioral | resume
    priority: float
    source: str  # role | resume | history | behavioral
    max_questions: int = 2

    @classmethod
    def from_dict(cls, d: dict) -> "PlanItem":
        return cls(**{k: d[k] for k in ("topic", "skill", "category", "priority", "source") if k in d},
                   max_questions=int(d.get("max_questions", 2)))


@dataclass
class TopicStat:
    asked: int = 0
    scores: list[float] = field(default_factory=list)
    weak_streak: int = 0
    strong_streak: int = 0
    status: str = "open"  # open | weak | strong | covered

    @property
    def average(self) -> float | None:
        return round(sum(self.scores) / len(self.scores), 2) if self.scores else None

    @classmethod
    def from_dict(cls, d: dict) -> "TopicStat":
        return cls(asked=d.get("asked", 0), scores=list(d.get("scores", [])), weak_streak=d.get("weak_streak", 0),
                   strong_streak=d.get("strong_streak", 0), status=d.get("status", "open"))


@dataclass(frozen=True)
class AdaptiveConfig:
    """Cut-offs used to read an evaluation as evidence. All criterion values are on the rubric's 0-10 scale."""

    # Evaluator confidence below this means the answer did not give enough evidence to judge (vague or ambiguous):
    # ask the candidate to clarify at the same difficulty instead of treating it as wrong.
    clarify_confidence: float = 0.5
    # Technical correctness at or above this, with concepts missing, means "right but incomplete": ask a targeted
    # follow-up on the missing concept rather than a generic probe or an easier question.
    gap_min_correctness: float = 6.0
    # Correctness and completeness at or above these count as a strong answer for difficulty purposes even when the
    # overall score is lower because the answer was short, so a concise but correct answer is not held back.
    concise_correct_min: float = 8.0
    concise_complete_min: float = 7.0

    @classmethod
    def from_settings(cls) -> "AdaptiveConfig":
        from app.core.config import get_settings

        s = get_settings()
        return cls(clarify_confidence=s.adaptive_clarify_confidence, gap_min_correctness=s.adaptive_gap_min_correctness,
                   concise_correct_min=s.adaptive_concise_correct_min,
                   concise_complete_min=s.adaptive_concise_complete_min)


@dataclass
class TurnEvidence:
    """What the last evaluation says about the answer (taken from the stored evaluation, never assumed)."""

    band: str
    overall: float
    technical_correctness: float
    completeness: float
    depth: float
    confidence: float
    missing_concepts: list[str] = field(default_factory=list)

    @classmethod
    def from_evaluation(cls, ev: dict | None) -> "TurnEvidence | None":
        if not ev or ev.get("band") is None:
            return None
        return cls(band=ev["band"], overall=float(ev.get("overall_score") or 0.0),
                   technical_correctness=float(ev.get("technical_correctness") or 0.0),
                   completeness=float(ev.get("completeness") or 0.0), depth=float(ev.get("depth") or 0.0),
                   confidence=float(ev.get("confidence") if ev.get("confidence") is not None else 1.0),
                   missing_concepts=[c for c in (ev.get("missing_concepts") or []) if c][:4])


def read_evidence(ev: TurnEvidence, cfg: AdaptiveConfig) -> tuple[str, str, str]:
    """Return (signal, effective_band, explanation) for one evaluated answer.

    signal: strong | concise_correct | gap | clarify | probe | misconception | weak
    effective_band drives the difficulty change (strong -> harder, weak -> easier, average -> same).
    """
    c, comp = ev.technical_correctness, ev.completeness
    scores = f"score {ev.overall:.0f}, correctness {c:g}/10, completeness {comp:g}/10, confidence {ev.confidence:.2f}"
    if ev.band == "strong":
        return "strong", "strong", f"Strong answer ({scores})"
    if c >= cfg.concise_correct_min and comp >= cfg.concise_complete_min:
        return "concise_correct", "strong", f"Correct and complete but brief answer ({scores}); not penalised for brevity"
    if ev.confidence < cfg.clarify_confidence:
        return "clarify", "average", f"Answer too vague or ambiguous to judge ({scores})"
    if c >= cfg.gap_min_correctness and ev.missing_concepts:
        return "gap", "average", f"Core idea correct but missing {', '.join(ev.missing_concepts[:2])} ({scores})"
    if ev.band == "weak":
        kind = "misconception" if c < cfg.gap_min_correctness else "weak"
        return kind, "weak", f"Weak answer ({scores})"
    return "probe", "average", f"Partially complete answer ({scores})"


_FOLLOW_UP = {
    "strong": ("follow_up_deeper", "probing deeper reasoning, application and trade-offs"),
    "concise_correct": ("follow_up_deeper", "raising the difficulty"),
    "gap": ("follow_up_gap", "asking specifically about the missing concept"),
    "clarify": ("follow_up_clarify", "asking the candidate to clarify with a concrete example"),
    "probe": ("follow_up_probe", "probing the gaps at similar difficulty"),
    "misconception": ("follow_up_foundational", "checking foundations with a simpler diagnostic question"),
    "weak": ("follow_up_foundational", "checking foundations with a simpler diagnostic question"),
}


@dataclass
class Decision:
    action: str  # ask | complete
    topic: str | None = None
    skill: str | None = None
    category: str | None = None
    difficulty: str | None = None
    # new_topic | follow_up_deeper | follow_up_probe | follow_up_gap | follow_up_clarify | follow_up_foundational
    kind: str | None = None
    reason: str = ""
    stop_reason: str | None = None
    focus: list[str] = field(default_factory=list)  # concepts the next question should target (from the evaluation)
    signal: str | None = None  # how the last answer was read (see read_evidence)

    def to_dict(self) -> dict:
        return asdict(self)


def shift_difficulty(current: str, band: str | None) -> str:
    """Strong → harder, average → same, weak → easier (bounded)."""
    idx = DIFFICULTIES.index(current) if current in DIFFICULTIES else 1
    if band == "strong":
        idx = min(idx + 1, len(DIFFICULTIES) - 1)
    elif band == "weak":
        idx = max(idx - 1, 0)
    return DIFFICULTIES[idx]


def update_topic_stat(stat: TopicStat, score: float, band: str) -> TopicStat:
    stat.asked += 1
    stat.scores.append(round(score, 2))
    if band == "weak":
        stat.weak_streak += 1
        stat.strong_streak = 0
    elif band == "strong":
        stat.strong_streak += 1
        stat.weak_streak = 0
    else:
        stat.weak_streak = 0
        stat.strong_streak = 0
    if stat.weak_streak >= WEAK_STREAK_TO_MARK:
        stat.status = "weak"
    elif stat.strong_streak >= STRONG_STREAK_TO_MARK:
        stat.status = "strong"
    return stat


def check_stop(*, asked: int, question_count: int, elapsed_seconds: float, duration_seconds: float,
               candidate_ended: bool = False, terminated: bool = False) -> str | None:
    if terminated:
        return "terminated_by_institution"
    if candidate_ended:
        return "ended_by_candidate"
    if asked >= question_count:
        return "question_count_reached"
    # Leave room for a final answer: stop when less than 45 s remain.
    if elapsed_seconds >= max(0.0, duration_seconds - 45):
        return "duration_reached"
    return None


def _pick_next_topic(plan: list[PlanItem], stats: dict[str, TopicStat], exclude: str | None) -> PlanItem | None:
    unvisited = [p for p in plan if stats.get(p.topic, TopicStat()).asked == 0 and p.topic != exclude]
    if unvisited:
        return sorted(unvisited, key=lambda p: (-p.priority, p.topic))[0]
    # All topics visited: revisit open (not weak/strong-marked) topics with headroom, lowest average first.
    revisitable = [p for p in plan if p.topic != exclude and stats.get(p.topic, TopicStat()).status == "open"
                   and stats.get(p.topic, TopicStat()).asked < p.max_questions + 1]
    if revisitable:
        return sorted(revisitable, key=lambda p: (stats[p.topic].average or 0.0, -p.priority, p.topic))[0]
    # Last resort: strong topics can still be probed at depth (application / trade-offs).
    strong = [p for p in plan if p.topic != exclude and stats.get(p.topic, TopicStat()).status == "strong"]
    if strong:
        return sorted(strong, key=lambda p: (stats[p.topic].asked, -p.priority))[0]
    return None


def decide_next(*, plan: list[PlanItem], stats: dict[str, TopicStat], current_topic: str | None,
                current_difficulty: str, last_band: str | None, asked: int, question_count: int,
                elapsed_seconds: float, duration_seconds: float, adaptive: bool,
                candidate_ended: bool = False, terminated: bool = False,
                evidence: TurnEvidence | None = None, config: AdaptiveConfig | None = None) -> Decision:
    stop = check_stop(asked=asked, question_count=question_count, elapsed_seconds=elapsed_seconds,
                      duration_seconds=duration_seconds, candidate_ended=candidate_ended, terminated=terminated)
    if stop:
        return Decision(action="complete", stop_reason=stop, reason=f"Interview complete: {stop.replace('_', ' ')}.")

    cfg = config or AdaptiveConfig()
    if evidence is not None:
        signal, eff_band, why_ev = read_evidence(evidence, cfg)
    elif last_band is not None:  # only the band is known (state saved before evidence was recorded)
        signal, eff_band, why_ev = {"strong": "strong", "weak": "weak"}.get(last_band, "probe"), last_band, ""
    else:
        signal, eff_band, why_ev = None, None, ""
    difficulty = shift_difficulty(current_difficulty, eff_band) if adaptive else current_difficulty
    remaining = question_count - asked
    by_topic = {p.topic: p for p in plan}
    unvisited_count = sum(1 for p in plan if stats.get(p.topic, TopicStat()).asked == 0)

    # First question, or no current topic: start with the highest-priority plan item.
    if current_topic is None or current_topic not in by_topic:
        nxt = _pick_next_topic(plan, stats, exclude=None)
        if nxt is None:
            return Decision(action="complete", stop_reason="plan_exhausted", reason="All planned topics covered.")
        return Decision(action="ask", topic=nxt.topic, skill=nxt.skill, category=nxt.category,
                        difficulty=difficulty, kind="new_topic",
                        reason=f"Starting with '{nxt.topic}' — highest-priority area (source: {nxt.source}).")

    item = by_topic[current_topic]
    stat = stats.get(current_topic, TopicStat())
    # Stay on the topic for a follow-up only when adaptive, not yet conclusive, under the per-topic cap,
    # and we can still afford to cover the unvisited topics.
    can_follow_up = (adaptive and stat.status == "open" and stat.asked < item.max_questions
                     and remaining > unvisited_count)
    if can_follow_up and signal is not None:
        kind, action_text = _FOLLOW_UP[signal]
        lead = why_ev or {"strong": "Strong answer", "weak": "Weak answer"}.get(last_band or "", "Partially complete answer")
        focus = list(evidence.missing_concepts) if evidence and kind in ("follow_up_gap", "follow_up_probe",
                                                                        "follow_up_foundational") else []
        return Decision(action="ask", topic=item.topic, skill=item.skill, category=item.category,
                        difficulty=difficulty, kind=kind, focus=focus, signal=signal,
                        reason=f"{lead}: {action_text} on '{item.topic}' at {difficulty} difficulty.")

    lead = f"{why_ev}. " if why_ev else ""
    if stat.status == "weak":
        transition = f"{lead}'{current_topic}' marked weak after repeated low scores; moving on to avoid repetition."
    elif stat.status == "strong":
        transition = f"{lead}'{current_topic}' marked strong; reducing repetition and moving on."
    else:
        transition = f"{lead}Coverage of '{current_topic}' sufficient for this interview."

    nxt = _pick_next_topic(plan, stats, exclude=current_topic)
    if nxt is None:
        if stat.status == "open" and stat.asked < item.max_questions + 1:
            return Decision(action="ask", topic=item.topic, skill=item.skill, category=item.category,
                            difficulty=difficulty, kind="follow_up_probe", signal=signal,
                            focus=list(evidence.missing_concepts) if evidence else [],
                            reason=f"{lead}No other topics remain; continuing on '{item.topic}'.")
        return Decision(action="complete", stop_reason="plan_exhausted", reason="All planned topics covered.")
    # A strong-marked topic revisited at the end is always asked at depth.
    if stats.get(nxt.topic, TopicStat()).status == "strong":
        difficulty = "hard"
    return Decision(action="ask", topic=nxt.topic, skill=nxt.skill, category=nxt.category, difficulty=difficulty,
                    kind="new_topic", signal=signal,
                    reason=f"{transition} Next: '{nxt.topic}' at {difficulty} difficulty (priority {nxt.priority:.2f}).")


def split_topics(stats: dict[str, TopicStat]) -> tuple[list[str], list[str]]:
    """Return (weak_topics, strong_topics) using marks and averages."""
    weak, strong = [], []
    for topic, s in stats.items():
        avg = s.average
        if s.status == "weak" or (avg is not None and avg < 50):
            weak.append(topic)
        elif s.status == "strong" or (avg is not None and avg >= 75):
            strong.append(topic)
    return sorted(weak), sorted(strong)
