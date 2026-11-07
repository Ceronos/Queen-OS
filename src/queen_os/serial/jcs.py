"""RFC 8785 JSON Canonicalization Scheme (JCS) — the byte layer of AF-SER-V1.

Differences from ``json.dumps(sort_keys=True)`` that matter for digests:

* Object keys are ordered by their UTF-16 code units, not by code point.
* Numbers use the ECMAScript ``Number.prototype.toString`` form (``1e+21``, ``1e-7``).
* Integers outside the IEEE-754 safe range are rejected: they cannot round-trip through
  other JCS implementations.

AF-SER-V1 additionally requires NFC strings. We refuse non-NFC input rather than
normalizing it, so canonicalization never silently changes the data it attests to.
"""

from __future__ import annotations

import math
import unicodedata
from decimal import Decimal
from typing import Any

MAX_SAFE_INT = 2**53 - 1

_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class CanonicalizationError(ValueError):
    """Raised when a value has no unambiguous canonical form. Callers must fail closed."""


def canonicalize(value: Any, *, require_nfc: bool = True) -> bytes:
    """Return the RFC 8785 canonical UTF-8 bytes for ``value``.

    ``require_nfc=False`` gives plain RFC 8785 (used for conformance vectors). Queen-OS
    state always uses the default.
    """
    parts: list[str] = []
    _emit(value, parts, require_nfc)
    return "".join(parts).encode("utf-8")


def _emit(value: Any, out: list[str], nfc: bool) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(_string(value, nfc))
    elif isinstance(value, int):
        out.append(_integer(value))
    elif isinstance(value, float):
        out.append(_float(value))
    elif isinstance(value, dict):
        _object(value, out, nfc)
    elif isinstance(value, (list, tuple)):
        _array(value, out, nfc)
    else:
        raise CanonicalizationError(f"type {type(value).__name__} is not JSON")


def _object(value: dict[Any, Any], out: list[str], nfc: bool) -> None:
    for key in value:
        if not isinstance(key, str):
            raise CanonicalizationError(f"object key {key!r} is not a string")
    out.append("{")
    for i, key in enumerate(sorted(value, key=_utf16_key)):
        if i:
            out.append(",")
        out.append(_string(key, nfc))
        out.append(":")
        _emit(value[key], out, nfc)
    out.append("}")


def _array(value: list[Any] | tuple[Any, ...], out: list[str], nfc: bool) -> None:
    out.append("[")
    for i, item in enumerate(value):
        if i:
            out.append(",")
        _emit(item, out, nfc)
    out.append("]")


def _utf16_key(key: str) -> bytes:
    return key.encode("utf-16-be", "surrogatepass")


def _string(value: str, nfc: bool = True) -> str:
    if nfc and not unicodedata.is_normalized("NFC", value):
        raise CanonicalizationError("string is not NFC-normalized (AF-SER-V1 rejects, never rewrites)")
    chars = []
    for ch in value:
        if ch in _ESCAPES:
            chars.append(_ESCAPES[ch])
        elif ord(ch) < 0x20:
            chars.append(f"\\u{ord(ch):04x}")
        elif 0xD800 <= ord(ch) <= 0xDFFF:
            raise CanonicalizationError("lone surrogate in string")
        else:
            chars.append(ch)
    return '"' + "".join(chars) + '"'


def _integer(value: int) -> str:
    if abs(value) <= MAX_SAFE_INT:
        return str(value)
    # JCS numbers are IEEE-754 doubles. A large int is admissible only if it is exactly
    # the number its canonical double text denotes. Otherwise the digest would attest a
    # value that other implementations read back differently.
    if abs(value) < 2**1024:
        text = _float(float(value))
        if Decimal(text) == value:
            return text
    raise CanonicalizationError(f"integer {value} has no exact canonical double form; encode it as a string")


def _float(value: float) -> str:
    if not math.isfinite(value):
        raise CanonicalizationError("NaN/Infinity have no JSON form")
    if value == 0:
        return "0"
    sign = "-" if value < 0 else ""
    # repr() is the shortest round-trip representation, the same digits ES6 picks.
    digits_tuple, exponent = _shortest_digits(abs(value))
    s = "".join(map(str, digits_tuple))
    k = len(s)
    n = exponent + k
    if k <= n <= 21:
        body = s + "0" * (n - k)
    elif 0 < n <= 21:
        body = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + s
    else:
        e = n - 1
        mantissa = s if k == 1 else s[0] + "." + s[1:]
        body = f"{mantissa}e{'+' if e >= 0 else '-'}{abs(e)}"
    return sign + body


def _shortest_digits(value: float) -> tuple[tuple[int, ...], int]:
    sign, digits, exponent = Decimal(repr(value)).as_tuple()
    assert isinstance(exponent, int)
    trimmed = list(digits)
    while len(trimmed) > 1 and trimmed[-1] == 0:
        trimmed.pop()
        exponent += 1
    return tuple(trimmed), exponent
