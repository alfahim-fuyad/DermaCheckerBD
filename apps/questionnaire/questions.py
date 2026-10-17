"""Skin warning signs questionnaire: ABCDE rule + ugly duckling + red-flag symptoms.

This is an EDUCATIONAL tool that helps the user self-assess whether a
skin lesion deserves professional review. It is NOT a diagnostic tool.

The questionnaire produces a 'concern level' (low / moderate / high) and
a list of specific recommendations. The user is always reminded that
only a qualified dermatologist can make a real diagnosis, and that
answering 'no' to everything does NOT guarantee the lesion is benign.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# Each question maps to a weight and (for red-flag questions) a hard
# override that forces 'high' concern regardless of the total score.
QUESTIONS = [
    {
        "id": "asymmetry",
        "label": "Asymmetry",
        "text": "Is one half of the lesion visibly different from the other half (shape, colour)?",
        "hint": "Imagine a line through the middle. Do the two halves match?",
        "weight": 2,
        "red_flag": False,
    },
    {
        "id": "border",
        "label": "Border irregularity",
        "text": "Are the edges of the lesion irregular, notched, scalloped, or blurred?",
        "hint": "Benign moles usually have smooth, even borders.",
        "weight": 2,
        "red_flag": False,
    },
    {
        "id": "colour",
        "label": "Colour variation",
        "text": "Does the lesion contain multiple colours or shades (brown, black, red, white, blue)?",
        "hint": "Uniform colour is typical of benign moles.",
        "weight": 2,
        "red_flag": False,
    },
    {
        "id": "diameter",
        "label": "Diameter",
        "text": "Is the lesion larger than 6 mm (about the size of a pencil eraser)?",
        "hint": "Measure with a ruler. Larger lesions warrant closer attention.",
        "weight": 1,
        "red_flag": False,
    },
    {
        "id": "evolving",
        "label": "Evolving",
        "text": "Has the lesion changed in size, shape, colour, or elevation in the last few weeks or months?",
        "hint": "Change is one of the strongest warning signs.",
        "weight": 3,
        "red_flag": False,
    },
    {
        "id": "ugly_duckling",
        "label": "Ugly duckling sign",
        "text": "Does this lesion look noticeably different from all your other moles?",
        "hint": "Each person's moles tend to look similar to one another.",
        "weight": 2,
        "red_flag": False,
    },
    {
        "id": "bleeding",
        "label": "Bleeding / oozing",
        "text": "Has the lesion bled, oozed, or crusted over without being scratched or injured?",
        "hint": "Spontaneous bleeding is a red flag.",
        "weight": 0,
        "red_flag": True,
    },
    {
        "id": "pain_itch",
        "label": "Pain / itching",
        "text": "Is the lesion persistently painful, tender, or itchy?",
        "hint": "Most benign moles are painless and not itchy.",
        "weight": 1,
        "red_flag": False,
    },
    {
        "id": "non_healing",
        "label": "Non-healing sore",
        "text": "Is there a sore on the lesion that has not healed in 3+ weeks?",
        "hint": "Skin cancers often present as sores that won't heal.",
        "weight": 0,
        "red_flag": True,
    },
    {
        "id": "new_after_40",
        "label": "New lesion after age 40",
        "text": "Is this a new lesion that appeared after age 40?",
        "hint": "Most benign moles appear in childhood or adolescence.",
        "weight": 1,
        "red_flag": False,
    },
]


@dataclass(frozen=True)
class QuestionnaireResult:
    concern_level: str          # 'low' | 'moderate' | 'high'
    total_score: int
    max_score: int
    red_flags_triggered: List[str]
    recommendations: List[str]
    answered_yes: List[str]
    answered_no: List[str]

    def as_dict(self) -> dict:
        return {
            "concern_level": self.concern_level,
            "total_score": self.total_score,
            "max_score": self.max_score,
            "red_flags_triggered": self.red_flags_triggered,
            "recommendations": self.recommendations,
            "answered_yes": self.answered_yes,
            "answered_no": self.answered_no,
        }


def evaluate(answers: dict, language: str = "en") -> QuestionnaireResult:
    """Evaluate the questionnaire answers.

    Args:
        answers: dict of question_id → 'yes' | 'no' | 'unsure' (or any value).
                 Only 'yes' counts toward the score; 'unsure' counts as 0.

    Returns:
        QuestionnaireResult with concern_level, score, and recommendations.
    """
    total_score = 0
    max_score = 0
    red_flags = []
    answered_yes = []
    answered_no = []

    for q in QUESTIONS:
        max_score += q["weight"]
        ans = (answers.get(q["id"], "") or "").strip().lower()
        if ans == "yes":
            total_score += q["weight"]
            answered_yes.append(q["id"])
            if q["red_flag"]:
                red_flags.append(q["id"])
        elif ans == "no":
            answered_no.append(q["id"])
        # 'unsure' / blank → 0 score, neither list

    # Concern level: red flags force HIGH; otherwise by score ratio.
    ratio = total_score / max_score if max_score > 0 else 0.0
    if red_flags or ratio >= 0.5:
        concern_level = "high"
    elif ratio >= 0.25:
        concern_level = "moderate"
    else:
        concern_level = "low"

    # Recommendations are generated server-side, so return them in the active
    # interface language rather than relying on a client-only text swap.
    if (language or "en").lower().startswith("bn"):
        recs = []
        if concern_level == "high":
            recs.append("আগামী কয়েক দিনের মধ্যে সরাসরি চর্মরোগ বিশেষজ্ঞের সময় নিন—কয়েক সপ্তাহ অপেক্ষা করবেন না। এই প্রশ্নমালার উত্তরগুলো সঙ্গে নিন।")
            if "bleeding" in red_flags:
                recs.append("আঘাত ছাড়া রক্তপাত একটি গুরুত্বপূর্ণ সতর্কসংকেত—চিকিৎসকের পরামর্শ নিতে দেরি করবেন না।")
            if "non_healing" in red_flags:
                recs.append("না-সারা ক্ষত দ্রুত চিকিৎসকের মাধ্যমে পরীক্ষা করানো উচিত, যাতে ত্বকের ক্যানসারসহ গুরুতর কারণ বাদ দেওয়া যায়।")
        elif concern_level == "moderate":
            recs.extend([
                "আগামী কয়েক সপ্তাহের মধ্যে নিয়মিত চর্মরোগ বিশেষজ্ঞের সময় নিন। আজই ছবি তুলে রাখুন, যাতে চিকিৎসক দাগটির বর্তমান অবস্থা দেখতে পারেন।",
                "প্রতি মাসে নিজে ত্বক পরীক্ষা চালিয়ে যান। অ্যাপয়েন্টমেন্টের আগে কোনো পরিবর্তন হলে আরও আগে চিকিৎসকের সঙ্গে যোগাযোগ করুন।",
            ])
        else:
            recs.extend([
                "কোনো সতর্কসংকেত জানানো হয়নি। ABCDE নিয়ম মেনে প্রতি মাসে ত্বক পরীক্ষা করুন।",
                "সতর্কসংকেত না থাকলেও কোনো দাগ নিয়ে উদ্বেগ হলে চিকিৎসকের পরামর্শ নিন। নিজের উদ্বেগকে গুরুত্ব দিন।",
            ])
        recs.append("এই প্রশ্নমালা শুধু শিক্ষামূলক; এটি পেশাদার চিকিৎসা-মূল্যায়নের বিকল্প নয়। নিশ্চিত মূল্যায়নের জন্য চর্মরোগ বিশেষজ্ঞ ডার্মোস্কোপি বা বায়োপসি করতে পারেন।")
        return QuestionnaireResult(
            concern_level=concern_level,
            total_score=total_score,
            max_score=max_score,
            red_flags_triggered=red_flags,
            recommendations=recs,
            answered_yes=answered_yes,
            answered_no=answered_no,
        )

    recs = []
    if concern_level == "high":
        recs.append(
            "Schedule an in-person dermatologist appointment within days, not weeks. "
            "Bring this questionnaire's answers with you."
        )
        if "bleeding" in red_flags:
            recs.append("Spontaneous bleeding is a significant warning sign — do not delay evaluation.")
        if "non_healing" in red_flags:
            recs.append("A non-healing sore warrants prompt professional examination to rule out skin cancer.")
    elif concern_level == "moderate":
        recs.append(
            "Schedule a routine dermatologist appointment within a few weeks. "
            "Take photos today so you can show the doctor how the lesion looks now."
        )
        recs.append(
            "Continue monthly self-examination. If anything changes before your appointment, move it sooner."
        )
    else:
        recs.append(
            "No warning signs reported. Continue monthly self-examination using the ABCDE rule."
        )
        recs.append(
            "Even with no warning signs, any lesion that concerns you deserves professional review. Trust your instincts."
        )
    recs.append(
        "This questionnaire is educational and does NOT replace a professional evaluation. "
        "A dermatologist may use dermoscopy or biopsy for a definitive assessment."
    )

    return QuestionnaireResult(
        concern_level=concern_level,
        total_score=total_score,
        max_score=max_score,
        red_flags_triggered=red_flags,
        recommendations=recs,
        answered_yes=answered_yes,
        answered_no=answered_no,
    )
