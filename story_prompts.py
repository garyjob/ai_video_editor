"""Narrative template text for Grok / planning (see docs/STORY_TEMPLATES.md)."""

from __future__ import annotations

from typing import Optional, Tuple

# Roast / make — Template 1 in STORY_TEMPLATES.md
ROAST_MAKE_USER_DIRECTION = (
    "Roasting cacao / chocolate with Mulan — cozy, authentic Agroverse kitchen story (not corporate). "
    "Instagram Reels: favor funny OR awe/delight (surprise, wonder, reactions, satisfying milestones). "
    "Clips are chronological; preserve time order when it helps the arc."
)

ROAST_MAKE_ADDITIONAL_CONTEXT = """
STORY TEMPLATE: Roast / make (kitchen transformation)

Try to cover these BEATS if the footage honestly supports them — roughly in order, skipping any beat with no good match:
1. Context — where we are; what we're doing (brief).
2. Heat / action — roasting, stirring, visceral motion.
3. Sensory hook — pop, smell, rhythm change; humor or tension welcome.
4. Hands-on craft — crack beans, winnow, grind, temper — specific technique.
5. Taste (nib / liquor) — first sensory verdict; awe or honest reaction.
6. Drink / final bite — hot chocolate or bar; emotional landing, comment or laugh.

CONSTRAINTS for ~30 seconds:
- Do NOT spend most of the runtime on one repetitive beat (e.g. same skillet angle over and over).
- Spread selections across MULTIPLE source files when available to reflect the full mini-arc.
- Prefer segments with visible faces + speech reactions for at least one beat when possible.
""".strip()

ROAST_HOT_CHOCOLATE_USER_DIRECTION = (
    "Roasting cacao through to hot chocolate with Mulan and family — cozy Agroverse kitchen arc. "
    "Instagram Reels: funny OR awe/delight where real. "
    "The story should move forward in time through roast → hands-on → tasting moments → brewing/pouring → sipping + reactions."
)

ROAST_HOT_CHOCOLATE_ADDITIONAL_CONTEXT = """
STORY TEMPLATE: Roast → hot chocolate (full drink payoff)

Prioritize a FORWARD arc ending with the cup:
1. Context — quick where/what.
2. Heat / roast / stir — but do not linger; one strong beat.
3. Sensory hook — pops, skin, humor if present.
4. Hands-on — crack/peel/nibs if footage supports it.
5. Brew / melt / froth — pot, boil, “like frosting,” pour setup.
6. PAYOFF — hot chocolate in cup; sip; reaction; comment (funny or warm).

CONSTRAINTS (~30s target, allow slight overrun if the line is landing):
- Use clips from MULTIPLE source files across the day; avoid skillet-only repetition.
- Prefer finishing a spoken thought when choosing in and out points (planner: avoid cutting mid-payoff).
- Chronological coherence: do not place an obviously earlier clip after a later one in the day.
""".strip()


def grok_prompts_for_template(
    template: Optional[str],
) -> Tuple[str, Optional[str]]:
    """
    Return (user_direction, additional_context) for Grok.
    ``template`` is lowercase strip: 'roast', 'roast_hot_chocolate', etc.
    """
    t = (template or "").strip().lower()
    if t in ("roast_hot_chocolate", "hot_chocolate", "roast_drink", "drink"):
        return ROAST_HOT_CHOCOLATE_USER_DIRECTION, ROAST_HOT_CHOCOLATE_ADDITIONAL_CONTEXT
    if t in ("roast", "roast_make", "make", "kitchen"):
        return ROAST_MAKE_USER_DIRECTION, ROAST_MAKE_ADDITIONAL_CONTEXT
    return (
        "Create an engaging vertical short from the analyzed clips. Vary shots; avoid repetition.",
        None,
    )
