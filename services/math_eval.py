"""Local math and unit conversion engine."""

import re

try:
    import sympy
    from sympy.parsing.sympy_parser import parse_expr, standard_transformations, implicit_multiplication_application
    from pint import UnitRegistry
    ureg = UnitRegistry()
except ImportError:
    sympy = None
    ureg = None

def _fmt_float(f: float) -> str:
    """Clean numeric formatting: integers as ints, floats trimmed (no 4.00000000)."""
    try:
        if f == int(f):
            return str(int(f))
        return f"{f:.10g}"
    except (ValueError, OverflowError):
        return str(f)


def _fmt_num(res) -> str:
    """Format a sympy number without trailing-zero noise."""
    try:
        if getattr(res, "is_Integer", False):
            return str(int(res))
        return _fmt_float(float(res.evalf()))
    except Exception:
        return str(res)


# Digital-storage units → (bytes, display label). Decimal (kB=1000) and binary
# (KiB=1024) kept distinct per SI/IEC; bits are 1/8 byte.
_DATA_UNITS = {
    "b": (1, "B"), "byte": (1, "B"), "bytes": (1, "B"),
    "bit": (0.125, "bit"), "bits": (0.125, "bit"),
    "kb": (1e3, "KB"), "kilobyte": (1e3, "KB"), "kilobytes": (1e3, "KB"),
    "mb": (1e6, "MB"), "megabyte": (1e6, "MB"), "megabytes": (1e6, "MB"),
    "gb": (1e9, "GB"), "gigabyte": (1e9, "GB"), "gigabytes": (1e9, "GB"),
    "tb": (1e12, "TB"), "terabyte": (1e12, "TB"), "terabytes": (1e12, "TB"),
    "pb": (1e15, "PB"), "petabyte": (1e15, "PB"), "petabytes": (1e15, "PB"),
    "kib": (2**10, "KiB"), "kibibyte": (2**10, "KiB"),
    "mib": (2**20, "MiB"), "mebibyte": (2**20, "MiB"),
    "gib": (2**30, "GiB"), "gibibyte": (2**30, "GiB"),
    "tib": (2**40, "TiB"), "tebibyte": (2**40, "TiB"),
}


def evaluate(query: str) -> str | None:
    if not sympy or not ureg:
        return None
        
    q = query.lower().strip()
    # Strip common natural language prefixes
    q = re.sub(r"^(what(?:'s|\s+is)\s+)?(?:calculate|compute|convert|solve)?\s*", "", q).strip()
    if not q:
        return None
    
    # 1. Handle "X% of Y"
    pct_match = re.match(r"([\d\.]+)\s*%\s*of\s+([\d\.]+)", q)
    if pct_match:
        try:
            res = float(pct_match.group(1)) / 100.0 * float(pct_match.group(2))
            return f"{pct_match.group(0)} = {_fmt_float(res)}"
        except Exception:
            pass

    # 1b. Temperature conversion — offset units need explicit Quantity handling,
    # and bare F/C must be read as degrees, not farad/coulomb.
    _TMAP = {"f": "degF", "fahrenheit": "degF", "degf": "degF",
             "c": "degC", "celsius": "degC", "degc": "degC",
             "k": "kelvin", "kelvin": "kelvin", "degk": "kelvin"}
    temp_match = re.match(
        r"(-?[\d\.]+)\s*°?\s*(f|c|k|fahrenheit|celsius|kelvin|degf|degc|degk)\b"
        r"\s+(?:to|in)\s+°?\s*(f|c|k|fahrenheit|celsius|kelvin|degf|degc|degk)\b", q)
    if temp_match:
        try:
            val, u_from, u_to = temp_match.groups()
            res = ureg.Quantity(float(val), _TMAP[u_from]).to(_TMAP[u_to])
            sym = {"degF": "°F", "degC": "°C", "kelvin": "K"}
            return (f"{_fmt_float(float(val))}{sym[_TMAP[u_from]]} = "
                    f"{_fmt_float(res.magnitude)}{sym[_TMAP[u_to]]}")
        except Exception:
            pass

    # 1c. Digital-storage conversion (gb/mb/kb/tb, binary gib/mib, bits/bytes) —
    # not in pint's default registry, so handle explicitly.
    data_match = re.match(r"(-?[\d\.]+)\s*([a-z]+)\s+(?:to|in)\s+([a-z]+)\b", q)
    if data_match:
        val, uf, ut = data_match.groups()
        if uf in _DATA_UNITS and ut in _DATA_UNITS:
            try:
                from_factor, from_lbl = _DATA_UNITS[uf]
                to_factor, to_lbl = _DATA_UNITS[ut]
                res = float(val) * from_factor / to_factor
                return f"{_fmt_float(float(val))} {from_lbl} = {_fmt_float(res)} {to_lbl}"
            except Exception:
                pass

    # 2. Try unit conversion: "val unit to unit"
    unit_match = re.search(r"([\d\.\seE+-]+[a-zA-Z_]+(?:[\s*/]+[a-zA-Z_]+)*)\s+(?:to|in)\s+([a-zA-Z_]+(?:[\s*/]+[a-zA-Z_]+)*)", q)
    if unit_match:
        try:
            val_from, val_to = unit_match.groups()
            qty = ureg(val_from)
            result = qty.to(val_to)
            return f"{qty:~P} = {_fmt_float(result.magnitude)} {result.units:~P}"
        except Exception:
            pass

    # 3. Try sympy for basic math
    # We only want to process queries that look somewhat like math 
    # to avoid treating regular sentences as math and throwing errors or evaluating weird things
    if not re.search(r'[\d]', q):
        return None

    try:
        transformations = standard_transformations + (implicit_multiplication_application,)
        clean_q = q.replace('^', '**').replace('×', '*').replace('÷', '/')
        res = parse_expr(clean_q, transformations=transformations, evaluate=True)
        if res.is_number:
            # Check if it's a very simple thing that just returns itself e.g., "5" -> 5
            has_op = bool(re.search(r"[+\-*/^%()]|sqrt|sin|cos|tan|log|exp", clean_q))
            if str(res) == clean_q.strip() and not has_op:
                return None
            return f"{q} = {_fmt_num(res)}"
        
        # We only want math results, not symbolic representations for text
        # If it returns a symbol and there are letters in original query, it might have just parsed "hello"
        if not res.is_number:
            return None
    except Exception:
        pass
        
    return None
