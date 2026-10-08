"""Generation failure — triggers a full restart (SH-FLOW-02)."""


class GenerationFailure(Exception):
    """Raised when a step cannot finish; the flow layer restarts generation.

    SH-FLOW-02: any failure restarts the whole generation (both sets, random
    stream continues). SH-FLOW-03 (port's 3-attempt cap) is deliberately NOT
    ported: we retry without limit. SH-FLOW-04 (restart drops the universal
    drops option) is a probable bug; options are kept across restarts.
    """
