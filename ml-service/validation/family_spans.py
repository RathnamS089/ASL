"""Ground truth for the Miacademy "ASL: Family" lesson (youtube.com/watch?v=N45u5W3rOBc),
taken from its manual English captions: each span runs from "The sign for X..." to the
start of the next sign's explanation, and the signer demonstrates X in it several times.
`islr` is the matching label in the pretrained model's 250-sign vocabulary, or None when
the sign is not in that vocabulary (the model cannot get those right by design).
"""
SPANS = [
    # (sign, start_s, end_s, islr_label)
    ("family", 70.2, 125.2, None),
    ("father", 125.2, 141.5, "dad"),
    ("mother", 141.5, 153.5, "mom"),
    ("grandpa", 153.5, 172.5, "grandpa"),
    ("grandma", 172.5, 188.1, "grandma"),
    ("brother", 188.1, 208.6, "brother"),
    ("sister", 208.6, 220.2, None),
    ("baby", 250.3, 268.3, None),
    ("aunt", 286.1, 302.0, "aunt"),
    ("uncle", 302.0, 318.6, "uncle"),
    ("cousin", 318.6, 333.2, None),
    ("friend", 337.8, 352.5, None),
    ("best friend", 352.5, 369.3, None),
    ("I love you", 369.3, 393.5, None),
]

# Review sections: signs performed in this order.
SEQUENCES = [
    ("review 1", 226.5, 244.2, ["family", "father", "mother", "grandpa", "grandma", "brother", "sister"]),
    ("review 2", 402.8, 419.7, ["baby", "aunt", "uncle", "cousin", "friend", "best friend", "I love you"]),
]
