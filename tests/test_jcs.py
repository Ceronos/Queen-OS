from __future__ import annotations

import json
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from queen_os.serial.jcs import MAX_SAFE_INT, CanonicalizationError, canonicalize

# RFC 8785 §3.2.3 / Appendix example
RFC_INPUT = (
    '{"numbers": [333333333.33333329, 1E30, 4.50, 2e-3, 0.000000000000000000000000001],'
    ' "string": "\\u20ac$\\u000F\\u000aA\'\\u0042\\u0022\\u005c\\\\\\"\\/",'
    ' "literals": [null, true, false]}'
)
RFC_OUTPUT = (
    '{"literals":[null,true,false],"numbers":[333333333.3333333,1e+30,4.5,0.002,1e-27],'
    '"string":"€$\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
)


def test_rfc8785_reference_example() -> None:
    assert canonicalize(json.loads(RFC_INPUT)).decode() == RFC_OUTPUT


def test_rfc8785_utf16_key_ordering() -> None:
    # RFC 8785 §3.2.3 sorting example: 😀 (U+1F600) sorts before U+FB33 in UTF-16,
    # the opposite of code-point order. U+FB33 is not NFC, hence require_nfc=False.
    obj = {
        "€": "Euro",
        "\r": "CR",
        "דּ": "Hebrew",
        "1": "One",
        "\U0001f600": "Smiley",
        "\u0080": "Control",
        "ö": "o-umlaut",
    }
    out = canonicalize(obj, require_nfc=False).decode()
    values = [v for v in json.loads(out, object_pairs_hook=lambda kv: [v for _, v in kv])]
    assert values == ["CR", "One", "Control", "o-umlaut", "Euro", "Smiley", "Hebrew"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "1"),
        (-1.5, "-1.5"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (5e-324, "5e-324"),
        (1.7976931348623157e308, "1.7976931348623157e+308"),
        (0.1 + 0.2, "0.30000000000000004"),
        (123456789012.5, "123456789012.5"),
        (-2.5e-10, "-2.5e-10"),
        (MAX_SAFE_INT, str(MAX_SAFE_INT)),
        (2**53, "9007199254740992"),
        (10**21, "1e+21"),
        (44746038704393020, "44746038704393020"),
    ],
)
def test_es6_number_format(value: float, expected: str) -> None:
    assert canonicalize(value).decode() == expected


@pytest.mark.parametrize(
    "bad",
    [math.nan, math.inf, -math.inf, MAX_SAFE_INT + 2, "é", {1: "x"}, {"s": {1, 2}}, b"bytes", "\ud800"],
)
def test_fail_closed_on_ambiguous_values(bad: object) -> None:
    with pytest.raises(CanonicalizationError):
        canonicalize(bad)


json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(-MAX_SAFE_INT, MAX_SAFE_INT)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text().map(lambda s: __import__("unicodedata").normalize("NFC", s)),
    lambda children: (
        st.lists(children, max_size=5)
        | st.dictionaries(st.text().map(lambda s: __import__("unicodedata").normalize("NFC", s)), children, max_size=5)
    ),
    max_leaves=25,
)


@given(json_values)
def test_canonical_form_is_a_fixed_point(value: object) -> None:
    first = canonicalize(value)
    assert canonicalize(json.loads(first)) == first


@given(
    st.dictionaries(
        st.text(alphabet=st.characters(max_codepoint=0x7F), max_size=8),
        st.integers(-MAX_SAFE_INT, MAX_SAFE_INT) | st.booleans() | st.none(),
        max_size=8,
    )
)
def test_agrees_with_stdlib_where_rules_coincide(value: dict[str, object]) -> None:
    expected = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert canonicalize(value) == expected
