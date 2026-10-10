"""Deciding whether a clause is something evidence could settle.

The fact-check desk needs assertions. A submission also contains headlines, photo
credits, questions, calls to action, the writer's own opinions and promises about
next year, and handing those to a desk produces either a confident verdict on
nothing or a desk that fails on input it should have refused.

Every rejection is returned rather than dropped, with a reason from
:class:`~app.domain.Unfit`, because "the extractor skipped your second paragraph"
and "the extractor thinks your second paragraph is opinion" are different messages
and only one of them is useful.

**What this does not decide is whether the claim is true.** "The moon is made of
cheese" passes every rule here. Checkability is about whether evidence *bears* on
the sentence; the verdict is somebody else's job, and conflating the two would let a
screening heuristic quietly veto claims it merely disagreed with.

On the opinion rule specifically: NLTK ships ``nltk.corpus.opinion_lexicon``, and it
is the wrong tool. It is Hu and Liu's *sentiment* lexicon, and sentiment is not
opinion — "the bridge collapsed", "the talks failed", "eleven people died" are all
strongly negative and all perfectly checkable. Scoring them as opinion would reject
exactly the reporting most worth checking. So the rule uses a small curated list of
*evaluative* words in *syntactic positions* where they carry the sentence's claim,
which is auditable in a way a 6,800-word sentiment list is not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain import Unfit
from app.nlp.split import Clause

if TYPE_CHECKING:  # pragma: no cover - spaCy is imported only by the pipeline
    from spacy.tokens import Token

#: Penn tags for a finite verb — past, present, third person, and modals. A clause
#: with none of these is not a sentence: "Photo by Reuters", "More on this story",
#: "Updated at 14:02". Note that spaCy tags copulas and auxiliaries with the same
#: set, so "The span is 3km" qualifies on ``is``.
_FINITE_TAGS = frozenset({"VBD", "VBP", "VBZ", "MD"})

_SUBJECTS = frozenset({"nsubj", "nsubjpass", "csubj", "csubjpass", "expl"})

#: Children that supply a verb with something to be about.
_CONTENT_DEPS = frozenset({"ccomp", "xcomp", "dobj", "dative", "attr", "acomp", "oprd"})

#: Modals that put the sentence in a world other than this one.
_HYPOTHETICAL_MODALS = frozenset({"would", "could", "might", "may", "should"})

#: Modals that put it in the future.
_FUTURE_MODALS = frozenset({"will", "shall"})

#: Subordinators that suspend the sentence's own commitment to its content.
_CONDITIONALS = frozenset({"if", "unless", "whether", "lest", "supposing"})

#: Verbs of stance, in the first person. "We believe the figure is wrong" asserts
#: something about the writer, not about the figure.
_STANCE_VERBS = frozenset(
    {
        "think",
        "believe",
        "feel",
        "reckon",
        "suppose",
        "doubt",
        "hope",
        "guess",
        "suspect",
        "fear",
        "wonder",
        "trust",
        "assume",
    }
)

#: Verbs of speech whose whole content is their complement. Chosen narrowly: verbs
#: that are fine on their own — "resigned", "testified", "responded to the report" —
#: are not here, because a clause built on them does assert something checkable.
_REPORTING_VERBS = frozenset(
    {
        "say",
        "state",
        "tell",
        "add",
        "remark",
        "comment",
        "declare",
        "claim",
        "allege",
        "insist",
        "deny",
        "confirm",
        "note",
    }
)

#: Evaluative adjectives: words whose application is a judgement rather than an
#: observation. Deliberately short and deliberately hand-picked — every entry is one
#: somebody could be asked to defend, and none of them is merely unpleasant.
_EVALUATIVE = frozenset(
    {
        "admirable",
        "appalling",
        "awful",
        "beautiful",
        "best",
        "better",
        "boring",
        "brilliant",
        "commendable",
        "deplorable",
        "disappointing",
        "disgraceful",
        "dreadful",
        "excellent",
        "exciting",
        "great",
        "hideous",
        "ideal",
        "impressive",
        "inexcusable",
        "laudable",
        "magnificent",
        "marvellous",
        "marvelous",
        "outrageous",
        "overrated",
        "perfect",
        "pointless",
        "praiseworthy",
        "remarkable",
        "ridiculous",
        "shameful",
        "silly",
        "splendid",
        "stupid",
        "superb",
        "terrible",
        "ugly",
        "unacceptable",
        "underrated",
        "unnecessary",
        "useless",
        "valuable",
        "wonderful",
        "worse",
        "worst",
        "worthless",
    }
)

#: Stance adverbs: the writer commenting on their own sentence. "Clearly the figure
#: is wrong" claims the figure is wrong *and* that this is obvious; the second half
#: is not checkable and its presence marks the first as argument rather than report.
_STANCE_ADVERBS = frozenset(
    {
        "admittedly",
        "arguably",
        "clearly",
        "curiously",
        "disappointingly",
        "frankly",
        "fortunately",
        "honestly",
        "hopefully",
        "inevitably",
        "obviously",
        "predictably",
        "presumably",
        "regrettably",
        "sadly",
        "shockingly",
        "surely",
        "surprisingly",
        "thankfully",
        "tragically",
        "unbelievably",
        "undoubtedly",
        "unfortunately",
        "worryingly",
    }
)


def screen(clause: Clause, *, min_tokens: int) -> tuple[bool, str]:
    """Return ``(checkable, reason)`` for one clause.

    ``reason`` is ``""`` when the clause is checkable and one of the
    :class:`~app.domain.Unfit` identifiers otherwise.

    The rules run in this order on purpose, cheapest and most certain first, and
    because several of them fire on the same sentence and the first one to fire is
    the one reported. "Why?" is a question *and* a fragment *and* too short; being
    told it is a question is the only one of those a person could act on. An
    imperative has no subject, so it would read as a fragment if the fragment rule
    ran earlier.
    """
    own = frozenset(token.i for token in clause.tokens)
    head = clause.head
    children = [child for child in head.children if child.i in own]

    if _is_question(clause):
        return False, Unfit.QUESTION
    if _is_imperative(head, children):
        return False, Unfit.IMPERATIVE
    if not _has_finite_verb(clause) or not _has_subject(children):
        return False, Unfit.FRAGMENT
    if _content_tokens(clause) < min_tokens:
        return False, Unfit.TOO_SHORT
    if _is_hypothetical(clause, children):
        return False, Unfit.HYPOTHETICAL
    if _is_prediction(children):
        return False, Unfit.PREDICTION
    if _is_opinion(clause, head, children):
        return False, Unfit.OPINION
    if _is_attribution_only(head, children):
        return False, Unfit.ATTRIBUTION_ONLY
    if not _names_anything(clause):
        return False, Unfit.NO_CONTENT
    return True, ""


# --------------------------------------------------------------- the nine ----


def _is_question(clause: Clause) -> bool:
    """A question mark anywhere in the clause, or the text ending in one.

    Both, because the rewritten text and the token run can disagree: a clause lifted
    out of "Did the bridge open, and what did it cost?" keeps no question mark of its
    own but is still interrogative in the source.
    """
    return clause.text.rstrip().endswith("?") or any(
        token.text == "?" for token in clause.tokens
    )


def _is_imperative(head: Token, children: list[Token]) -> bool:
    """A bare-form verb heading a clause with no subject and no auxiliary.

    The auxiliary test is what separates "Read the report" from the infinitival
    fragment "To read the report" — both are ``VB`` with no subject, and only the
    first is an instruction.
    """
    if head.pos_ != "VERB" or head.tag_ != "VB":
        return False
    if any(child.dep_ in _SUBJECTS for child in children):
        return False
    return not any(child.dep_ in {"aux", "auxpass"} for child in children)


def _has_finite_verb(clause: Clause) -> bool:
    return any(token.tag_ in _FINITE_TAGS for token in clause.tokens)


def _has_subject(children: list[Token]) -> bool:
    return any(child.dep_ in _SUBJECTS for child in children)


def _content_tokens(clause: Clause) -> int:
    """How many tokens carry content: words, named tokens and numbers."""
    return sum(
        1
        for token in clause.tokens
        if (token.is_alpha or token.like_num or token.pos_ in {"NOUN", "PROPN"})
        and not token.is_space
    )


def _is_hypothetical(clause: Clause, children: list[Token]) -> bool:
    """Conditional or counterfactual: the clause does not commit to its content."""
    if any(
        token.dep_ == "mark" and token.lemma_.lower() in _CONDITIONALS
        for token in clause.tokens
    ):
        return True
    return any(
        child.tag_ == "MD" and child.lemma_.lower() in _HYPOTHETICAL_MODALS
        for child in children
    )


def _is_prediction(children: list[Token]) -> bool:
    """About the future — not checkable *yet*, which is a different thing.

    Only ``will``/``shall`` and the ``be going to`` construction. Verbs like "plan"
    and "expect" are excluded on purpose: "The council plans to widen the road" is a
    present-tense claim about a plan, and the plan either exists or does not.
    """
    if any(
        child.tag_ == "MD" and child.lemma_.lower() in _FUTURE_MODALS
        for child in children
    ):
        return True
    return any(
        child.dep_ == "xcomp"
        and child.head.lemma_.lower() == "go"
        and any(
            sub.dep_ == "aux" and sub.lemma_.lower() == "to" for sub in child.children
        )
        for child in children
    )


def _is_opinion(clause: Clause, head: Token, children: list[Token]) -> bool:
    """The writer's stance, or a judgement standing where the assertion should be."""
    # "I think", "we believe" — a claim about the writer.
    if head.lemma_.lower() in _STANCE_VERBS and any(
        child.dep_ in _SUBJECTS
        and child.pos_ == "PRON"
        and child.lemma_.lower() in {"i", "we"}
        for child in children
    ):
        return True
    # "The bridge is beautiful" — the judgement is the predicate, so it is the claim.
    if any(
        child.dep_ in {"acomp", "attr"} and child.lemma_.lower() in _EVALUATIVE
        for child in children
    ):
        return True
    # "Obviously the figure is wrong" — the writer arguing rather than reporting.
    return any(
        token.dep_ == "advmod" and token.lemma_.lower() in _STANCE_ADVERBS
        for token in clause.tokens
    )


def _is_attribution_only(head: Token, children: list[Token]) -> bool:
    """Reports that somebody spoke without reporting what they said."""
    if head.lemma_.lower() not in _REPORTING_VERBS:
        return False
    return not any(child.dep_ in _CONTENT_DEPS for child in children)


def _names_anything(clause: Clause) -> bool:
    """Whether there is anything here evidence could be found *about*.

    "It happened." parses cleanly, has a subject and a finite verb, and gives a desk
    nothing whatsoever to look up. A named entity, a number, or any nominal that is
    not a pronoun is enough.
    """
    for token in clause.tokens:
        if token.ent_type_:
            return True
        if token.like_num:
            return True
        if token.pos_ in {"NOUN", "PROPN"}:
            return True
    return False
