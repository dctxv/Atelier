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
            return f"{pct_match.group(0)} = {res}"
        except Exception:
            pass

    # 2. Try unit conversion: "val unit to unit"
    unit_match = re.search(r"([\d\.\seE+-]+[a-zA-Z_]+(?:[\s*/]+[a-zA-Z_]+)*)\s+(?:to|in)\s+([a-zA-Z_]+(?:[\s*/]+[a-zA-Z_]+)*)", q)
    if unit_match:
        try:
            val_from, val_to = unit_match.groups()
            qty = ureg(val_from)
            result = qty.to(val_to)
            return f"{qty} = {result:~P}"
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
            if str(res) == clean_q.strip():
                return None
            return f"{q} = {res.evalf()}"
        
        # We only want math results, not symbolic representations for text
        # If it returns a symbol and there are letters in original query, it might have just parsed "hello"
        if not res.is_number:
            return None
    except Exception:
        pass
        
    return None
