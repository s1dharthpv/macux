"""MacUX Spotlight — safe arithmetic expression evaluator.

Evaluates numeric expressions using Python's AST (no eval()).
Supports:
  - Basic arithmetic:   2 + 3 * 4,  100 / 7,  2 ^ 8
  - Unary minus:        -5,  -(3 + 2)
  - Math functions:     sqrt(16), sin(30), cos(45), log(100), ceil(1.4)
  - Constants:          pi, e, tau, inf
  - Modulo:             17 % 5
  - Implicit multiply:  2pi, 3e  (not supported — keeps it simple)

The caller should use `is_arithmetic(query)` first to avoid evaluating
every Spotlight keystroke.  Evaluation is fast (< 1 ms) but we only
want to show a calculator result when the user clearly intends math.
"""

from __future__ import annotations

import ast
import math
import operator
import re
from typing import Any

# Allowed AST node types (whitelist)
_SAFE_NODES = (
    ast.Module, ast.Expr, ast.Expression,
    ast.BinOp, ast.UnaryOp, ast.BoolOp,
    ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.USub, ast.UAdd,
    ast.Call, ast.Name, ast.Load,
)

# Allowed names that may appear in an expression
_SAFE_NAMES: dict[str, Any] = {
    # Constants
    "pi":   math.pi,
    "e":    math.e,
    "tau":  math.tau,
    "inf":  math.inf,
    # Functions (1-arg)
    "sqrt": math.sqrt,
    "sin":  lambda x: math.sin(math.radians(x)),
    "cos":  lambda x: math.cos(math.radians(x)),
    "tan":  lambda x: math.tan(math.radians(x)),
    "asin": lambda x: math.degrees(math.asin(x)),
    "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)),
    "log":  math.log10,
    "ln":   math.log,
    "log2": math.log2,
    "abs":  abs,
    "ceil": math.ceil,
    "floor": math.floor,
    "round": round,
    "exp":  math.exp,
    "factorial": math.factorial,
}

# Pattern that strongly suggests an arithmetic expression
_ARITHMETIC_RE = re.compile(
    r"^\s*"
    r"(?:"
    r"[\d\.\+\-\*\/\^\(\)\%\s]+"          # digits and operators
    r"|(?:" + "|".join(_SAFE_NAMES) + r")\s*\("  # known function calls
    r")"
    r"[\d\.\+\-\*\/\^\(\)\%\s\w]*"
    r"\s*$",
    re.IGNORECASE,
)


class CalculatorError(Exception):
    """Raised when the expression cannot be evaluated safely."""


def is_arithmetic(query: str) -> bool:
    """
    Return True if ``query`` looks like a math expression worth evaluating.

    Uses a fast regex pre-filter — does NOT guarantee the expression is valid.
    """
    q = query.strip()
    if not q:
        return False

    # Must contain at least one digit or known function
    has_digit = any(c.isdigit() for c in q)
    has_func = any(q.lower().startswith(fn + "(") for fn in _SAFE_NAMES)

    if not (has_digit or has_func):
        return False

    # ^ is not standard Python — normalise for the regex check
    q_norm = q.replace("^", "**")
    return bool(_ARITHMETIC_RE.match(q_norm))


def evaluate(expression: str) -> str:
    """
    Evaluate a math expression and return the result as a string.

    Args:
        expression: Expression string, e.g. "2 + 3 * 4" or "sqrt(16)".

    Returns:
        Human-readable result string, e.g. "14" or "4.0".

    Raises:
        CalculatorError: If the expression is unsafe or syntactically invalid.
    """
    # Normalise: replace ^ with ** (caret power)
    expr = expression.strip().replace("^", "**")

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CalculatorError(f"Syntax error: {exc}") from exc

    _assert_safe(tree)

    try:
        result = _eval_node(tree.body)
    except ZeroDivisionError:
        raise CalculatorError("Division by zero")
    except (ValueError, OverflowError, TypeError) as exc:
        raise CalculatorError(str(exc)) from exc

    return _format_result(result)


# ── Internal ──────────────────────────────────────────────────────────────────

def _assert_safe(node: ast.AST) -> None:
    """Recursively verify all AST nodes are in the whitelist."""
    if not isinstance(node, _SAFE_NODES):
        raise CalculatorError(
            f"Unsafe expression: {type(node).__name__} is not allowed"
        )
    for child in ast.iter_child_nodes(node):
        _assert_safe(child)


def _eval_node(node: ast.expr) -> Any:
    """Recursively evaluate a whitelisted AST expression node."""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float, complex)):
            raise CalculatorError("Only numeric literals are allowed")
        return node.value

    if isinstance(node, ast.Name):
        name = node.id.lower()
        if name not in _SAFE_NAMES:
            raise CalculatorError(f"Unknown name: {node.id!r}")
        return _SAFE_NAMES[name]

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return operand
        raise CalculatorError(f"Unsupported unary op: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        _BINOPS = {
            ast.Add:      operator.add,
            ast.Sub:      operator.sub,
            ast.Mult:     operator.mul,
            ast.Div:      operator.truediv,
            ast.FloorDiv: operator.floordiv,
            ast.Mod:      operator.mod,
            ast.Pow:      operator.pow,
        }
        fn = _BINOPS.get(type(node.op))
        if fn is None:
            raise CalculatorError(f"Unsupported operator: {type(node.op).__name__}")
        return fn(left, right)

    if isinstance(node, ast.Call):
        func = _eval_node(node.func)
        if not callable(func):
            raise CalculatorError("Attempted to call a non-function")
        if node.keywords:
            raise CalculatorError("Keyword arguments not allowed")
        args = [_eval_node(a) for a in node.args]
        return func(*args)

    raise CalculatorError(f"Unsupported node: {type(node).__name__}")


def _format_result(value: Any) -> str:
    """Format a numeric result for display."""
    if isinstance(value, complex):
        r, i = value.real, value.imag
        if i == 0:
            return _format_float(r)
        sign = "+" if i >= 0 else "-"
        return f"{_format_float(r)} {sign} {_format_float(abs(i))}i"

    if isinstance(value, bool):
        return str(value)

    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")  # thin-space thousands separator

    if isinstance(value, float):
        return _format_float(value)

    return str(value)


def _format_float(value: float) -> str:
    """Round to 10 significant digits and strip trailing zeros."""
    if math.isinf(value):
        return "∞" if value > 0 else "-∞"
    if math.isnan(value):
        return "NaN"
    # Use 10 significant digits
    formatted = f"{value:.10g}"
    # Remove redundant trailing zeros after decimal point
    if "." in formatted and "e" not in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted
