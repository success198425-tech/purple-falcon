# ==================================================
# 🧠 PURPLE FALCON PH — FALLBACK REASONING (DOLA-style layers)
#    When the main AI is unreachable, use multi-layer reasoning
#    to synthesize evidence from live web sources.
# ==================================================
import re
import time
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ReasoningLayer:
    """Each layer adds confidence to the final answer."""
    name: str                    # "source_alignment", "temporal_consistency", etc.
    confidence: float            # 0..1 how well this layer agrees
    evidence: str                # explanation
    applicable: bool = True      # whether this layer applies to this query


def analyze_source_alignment(evidence_list) -> ReasoningLayer:
    """Do multiple sources agree on key facts?"""
    if len(evidence_list) < 2:
        return ReasoningLayer("source_alignment", 0.5, "Only one source available", applicable=False)
    
    # Extract key numbers/dates from evidence
    facts = []
    for e in evidence_list:
        numbers = re.findall(r'\d+(?:\.\d+)?', e.text)
        facts.append((e.source, set(numbers)))
    
    # Check for overlap
    all_numbers = set()
    for _, nums in facts:
        all_numbers.update(nums)
    
    agreement = len([f for f in facts if len(f[1]) > 0]) / len(facts) if facts else 0
    confidence = 0.7 + (0.3 * agreement)
    
    return ReasoningLayer(
        "source_alignment",
        confidence,
        f"{len(evidence_list)} sources found {len(all_numbers)} unique data points"
    )


def analyze_temporal_consistency(evidence_list) -> ReasoningLayer:
    """Are facts from recent sources? Do they contradict each other temporally?"""
    if not evidence_list:
        return ReasoningLayer("temporal_consistency", 0.5, "No evidence to check", applicable=False)
    
    now = time.time()
    ages = [(now - e.fetched) / 3600 for e in evidence_list]  # in hours
    avg_age = sum(ages) / len(ages) if ages else 0
    
    # Freshness score: recent = higher confidence
    if avg_age < 1:
        freshness = 0.95
        desc = "All sources refreshed within the last hour"
    elif avg_age < 24:
        freshness = 0.85
        desc = f"Average age: {avg_age:.1f} hours"
    elif avg_age < 7 * 24:
        freshness = 0.65
        desc = f"Some sources are {avg_age/24:.1f} days old"
    else:
        freshness = 0.4
        desc = f"Sources are {avg_age/(24*7):.1f} weeks old — may be outdated"
    
    return ReasoningLayer("temporal_consistency", freshness, desc)


def analyze_specificity(question: str, evidence_list) -> ReasoningLayer:
    """How specific/targeted was the answer?"""
    if not evidence_list:
        return ReasoningLayer("specificity", 0.5, "No evidence", applicable=False)
    
    # Longer, more detailed answers = more specific
    avg_text_len = sum(len(e.text) for e in evidence_list) / len(evidence_list)
    
    # Questions with proper nouns expect more specific answers
    proper_nouns = len(re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question))
    
    specificity = min(0.95, 0.5 + (avg_text_len / 500) + (proper_nouns * 0.1))
    
    return ReasoningLayer(
        "specificity",
        specificity,
        f"Answer depth: {avg_text_len:.0f} chars, {len(evidence_list)} sources, {proper_nouns} named entities"
    )


def analyze_contradiction_risk(evidence_list) -> ReasoningLayer:
    """Do sources contradict each other?"""
    if len(evidence_list) < 2:
        return ReasoningLayer("contradiction_risk", 0.8, "Single source — no contradiction risk", applicable=False)
    
    # Look for conflicting statements (very simple heuristic)
    common_negators = {'not', 'never', 'no', 'false', 'wrong', 'denied', 'rejected'}
    
    contradiction_count = 0
    for i, e1 in enumerate(evidence_list):
        for e2 in evidence_list[i+1:]:
            text1_words = set(e1.text.lower().split())
            text2_words = set(e2.text.lower().split())
            
            # Simple check: if one says "yes" and other says "no"
            if text1_words & common_negators and not (text2_words & common_negators):
                contradiction_count += 1
    
    confidence = max(0.5, 1.0 - (contradiction_count * 0.2))
    
    return ReasoningLayer(
        "contradiction_risk",
        confidence,
        f"Checked {len(evidence_list)} sources for contradictions"
    )


def fallback_reasoning(question: str, evidence_list, max_layers=4):
    """
    Multi-layer reasoning when AI is unavailable.
    Returns: (composite_confidence, reasoning_explanation, layers)
    """
    layers = [
        analyze_source_alignment(evidence_list),
        analyze_temporal_consistency(evidence_list),
        analyze_specificity(question, evidence_list),
        analyze_contradiction_risk(evidence_list),
    ]
    
    # Keep only applicable layers
    active = [l for l in layers if l.applicable][:max_layers]
    
    # Confidence = average of active layers (with early layers weighted higher)
    if active:
        confidence = sum(l.confidence * (2 - i/len(active)) for i, l in enumerate(active)) / (len(active) * 1.5)
        confidence = min(1.0, max(0.3, confidence))
    else:
        confidence = 0.5
    
    explanation = f"**Reasoning ({confidence*100:.0f}% confidence)**:\n"
    for layer in active:
        symbol = "✓" if layer.confidence > 0.7 else "◐" if layer.confidence > 0.4 else "✗"
        explanation += f"• {symbol} {layer.name}: {layer.evidence}\n"
    
    return confidence, explanation, active


def compose_with_reasoning(res, intro=None, show_reasoning=True):
    """
    Enhanced compose() that adds fallback reasoning layers.
    Use when the main AI model is unavailable.
    """
    if not res.evidence:
        from falcon_skills import friendly_fallback
        return friendly_fallback(res.question)
    
    from falcon_skills import _GENERIC_SKILLS, sources_footer
    
    specific = [e for e in res.evidence if e.skill not in _GENERIC_SKILLS]
    chosen = specific[:2] if specific else res.evidence[:3]
    
    L = [intro or "🔎 Here's what I found live:"]
    
    # Main answer from evidence
    for e in chosen:
        L += ["", f"**{e.title}**" if e.title else "", e.text]
        if e.stale:
            L.append("*(from my memory — I couldn't refresh it just now)*")
        elif e.cached:
            L.append("*(from my memory)*")
    
    # Add reasoning layers
    if show_reasoning and len(res.evidence) > 1:
        confidence, reasoning_text, layers = fallback_reasoning(
            res.question, chosen
        )
        L += ["", reasoning_text]
        
        # Confidence warning if low
        if confidence < 0.6:
            L.append(f"⚠️ **Confidence is {confidence*100:.0f}%** — consider verifying with another source")
    
    # Sources
    foot = sources_footer(type(res)(res.question, chosen))
    if foot:
        L += ["", foot]
    
    return "\n".join(x for x in L if x is not None)


if __name__ == "__main__":
    # Example usage
    from falcon_skills import research, Evidence
    
    # Simulate a research result
    test_res = research("capital of France", generic=True)
    
    if test_res.evidence:
        answer = compose_with_reasoning(test_res)
        print(answer)
    else:
        print("No evidence found")
