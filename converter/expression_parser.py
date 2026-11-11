import re
from typing import Tuple, List, Optional, Set

def parse_uipath_duration(duration_str: str) -> float:
    """
    Parse UiPath duration string like '00:00:05' or '00:01:30.500' into seconds.
    If already a number, returns that number.
    """
    if not duration_str:
        return 1.0
    s = duration_str.strip().strip('"').strip("'").strip("[]")
    if s == "{x:Null}":
        return 0.0
        
    try:
        return float(s)
    except ValueError:
        pass
        
    match = re.match(r'(?:(\d+):)?(\d{1,2}):(\d{1,2}(?:\.\d+)?)', s)
    if match:
        h = float(match.group(1)) if match.group(1) else 0.0
        m = float(match.group(2))
        sec = float(match.group(3))
        return h * 3600 + m * 60 + sec
        
    return 1.0

def clean_uipath_expression(raw_expr: str) -> str:
    """Clean brackets, null tokens, and whitespace around UiPath expressions."""
    if not raw_expr:
        return ""
    expr = raw_expr.strip()
    if expr in ["{x:Null}", "{x:Reference ...}"]:
        return ""
    if expr.startswith('[') and expr.endswith(']'):
        expr = expr[1:-1].strip()
    return expr

def has_unquoted_operator(s: str) -> bool:
    """Check if string contains unquoted + or & concatenation operators."""
    in_quote = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"':
            if in_quote and i + 1 < len(s) and s[i+1] == '"':
                i += 1  # Skip escaped quote ""
            else:
                in_quote = not in_quote
        elif not in_quote and ch in ['+', '&']:
            return True
        i += 1
    return False

def split_unquoted_concat(s: str) -> List[str]:
    """Split string on + or & outside of double quotes."""
    parts = []
    current = []
    in_quote = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '"':
            if in_quote and i + 1 < len(s) and s[i+1] == '"':
                current.append('""')
                i += 1
            else:
                in_quote = not in_quote
                current.append(ch)
        elif not in_quote and ch in ['+', '&']:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]

def convert_uipath_expression_to_robin(raw_expr: str) -> str:
    """
    Convert a UiPath VB.NET/C# expression or attribute value to a Power Automate Robin value.
    Rules:
      - If {x:Null}, return $''''''
      - If wrapped in brackets '[...]', it is a UiPath expression or variable binding.
      - If NOT wrapped in brackets, it is a literal string/number from XAML attributes.
    """
    if not raw_expr:
        return "$''''''"
        
    raw_stripped = raw_expr.strip()
    if raw_stripped in ["{x:Null}", "Nothing"]:
        return "$''''''"
        
    has_brackets = raw_stripped.startswith('[') and raw_stripped.endswith(']')
    expr = clean_uipath_expression(raw_expr)
    if not expr or expr in ['""', "''"]:
        return "$''''''"
    
    # Check if purely boolean
    if expr.lower() in ['true', 'false']:
        return "True" if expr.lower() == 'true' else "False"
        
    # Check if purely integer or float
    if re.match(r'^-?\d+(?:\.\d+)?$', expr):
        return expr

    # If NOT in brackets, it is a plain attribute literal value
    if not has_brackets:
        single_str = re.match(r'^"([^"]*)"$', expr)
        if single_str:
            return f"$'''{single_str.group(1)}'''"
        return f"$'''{expr}'''"
        
    # --- From here on, has_brackets is TRUE (Expression context) ---

    clean_expr_str = expr.strip()

    # 1. Check for .NET instantiations: new JObject(), New JArray(), New List(...), New DataTable()
    if re.match(r'^new\s+jobject(\(\))?$', clean_expr_str, re.IGNORECASE):
        return "$'''{}'''"
    if re.match(r'^new\s+(?:jarray|list\b)(\(\))?$', clean_expr_str, re.IGNORECASE):
        return "[]"
    if re.match(r'^new\s+(?:system\.data\.)?datatable(\(\))?$', clean_expr_str, re.IGNORECASE):
        return "$''''''"

    # 2. Check for Path.Combine(...)
    m_path = re.search(r'Path\.Combine\s*\([^,]+,\s*"([^"]+)"\)', clean_expr_str, re.DOTALL)
    if m_path:
        fname = m_path.group(1)
        return f"$'''%SpecialFolderPath%\\{fname}'''"

    # 3. Check for VB array literal { ... } (e.g. AddDataRow ArrayRow)
    if clean_expr_str.startswith('{') and clean_expr_str.endswith('}'):
        inner_arr = clean_expr_str[1:-1].strip()
        items = [i.strip() for i in re.split(r',\s*(?![^()]*\))', inner_arr) if i.strip()]
        robin_items = []
        for item in items:
            m_tok = re.match(r'^([a-zA-Z0-9_]+)\("([^"]+)"\)(?:\.ToString(?:\(\))?)?$', item)
            if m_tok:
                tok_obj = "CurrentItem" if m_tok.group(1) == "currentJToken" else m_tok.group(1)
                robin_items.append(f"{tok_obj}['{m_tok.group(2)}']")
            elif item.endswith(".ToString") or item.endswith(".ToString()"):
                v = re.sub(r'\.ToString(?:\(\))?$', '', item).strip()
                robin_items.append(v)
            else:
                robin_items.append(item)
        return "[" + ", ".join(robin_items) + "]"

    # 4. Check if a single string literal with quotes: e.g. ["Hello World"] or JSON string ["{""id"": 1}"]
    if clean_expr_str.startswith('"') and clean_expr_str.endswith('"') and len(clean_expr_str) >= 2:
        if not has_unquoted_operator(clean_expr_str):
            inner = clean_expr_str[1:-1].replace('""', '"')
            if inner.strip().startswith('{') and inner.strip().endswith('}'):
                inner_collapsed = re.sub(r'[\r\n]+', '', inner)
            else:
                inner_collapsed = inner.replace('\r\n', '\\r\\n').replace('\n', '\\r\\n')
            return f"$'''{inner_collapsed}'''"

    # Pre-clean common VB.NET idioms
    # Replace escaped quotes in VB: "" -> "
    vb_clean = expr.replace('""', '"')
    
    # Check if string interpolation $"Hello {name}"
    interp_match = re.match(r'^\$"([^"]*)"$', vb_clean, re.DOTALL)
    if interp_match:
        content = interp_match.group(1)
        replaced = re.sub(r'\{([a-zA-Z0-9_]+)\}', r'%\1%', content)
        return f"$'''{replaced}'''"

    # Check if simple variable identifier: e.g. [searchQuery] -> bare variable name in Robin expressions
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', expr):
        return expr

    # Token access like jsonObj("title").ToString or currentJToken("body").ToString
    token_match = re.match(r'^([a-zA-Z0-9_]+)\("([^"]+)"\)(?:\.ToString(?:\(\))?)?$', expr)
    if token_match:
        var_obj = token_match.group(1)
        var_key = token_match.group(2)
        if var_obj == "currentJToken":
            return f"CurrentItem['{var_key}']"
        return f"{var_obj}['{var_key}']"

    # Check if string concatenation: "prefix " + var + " suffix" or & in VB
    if has_unquoted_operator(clean_expr_str):
        parts = split_unquoted_concat(clean_expr_str)
        if len(parts) > 1:
            text_builder = []
            is_all_text_and_vars = True
            for p in parts:
                p_strip = p.strip()
                if p_strip in ["vbCrLf", "Environment.NewLine"]:
                    text_builder.append("\\r\\n")
                elif p_strip.startswith('"') and p_strip.endswith('"'):
                    text_builder.append(p_strip[1:-1].replace('""', '"'))
                elif re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', p_strip):
                    text_builder.append(f"%{p_strip}%")
                elif p_strip.endswith(".ToString") or p_strip.endswith(".ToString()"):
                    v = re.sub(r'\.ToString(?:\(\))?$', '', p_strip).strip()
                    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', v):
                        text_builder.append(f"%{v}%")
                    else:
                        m_tok = re.match(r'^([a-zA-Z0-9_]+)\("([^"]+)"\)$', v)
                        if m_tok:
                            tok_obj = "CurrentItem" if m_tok.group(1) == "currentJToken" else m_tok.group(1)
                            text_builder.append(f"%{tok_obj}['{m_tok.group(2)}']%")
                        else:
                            text_builder.append(f"%{v}%")
                elif re.match(r'^([a-zA-Z0-9_]+)\("([^"]+)"\)', p_strip):
                    m_tok = re.match(r'^([a-zA-Z0-9_]+)\("([^"]+)"\)', p_strip)
                    tok_obj = "CurrentItem" if m_tok.group(1) == "currentJToken" else m_tok.group(1)
                    text_builder.append(f"%{tok_obj}['{m_tok.group(2)}']%")
                else:
                    is_all_text_and_vars = False
                    break
                    
            if is_all_text_and_vars:
                combined = "".join(text_builder).replace("\r\n", "\\r\\n").replace("\n", "\\r\\n")
                return f"$'''{combined}'''"

    # Arithmetic/property expression: rowCount + 1, x - 5, count * 2, jsonArray.Count
    if re.match(r'^[a-zA-Z0-9_\s\+\-\*\/\(\)\.]+$', expr) and not any(k in expr for k in ["new ", "New "]):
        return expr

    # General expression outside string quotes stays bare (never wrapped in %...%)
    return expr

_NUMERIC_CAST_RE = re.compile(
    r'\b(?:CInt|CLng|CSng|CDbl|Convert\.ToInt32|Convert\.ToInt64|Convert\.ToDouble|Convert\.ToDecimal|Int32\.Parse|Double\.Parse|Decimal\.Parse)\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)',
    re.IGNORECASE,
)


def _convert_condition_core(
    raw_cond: str,
    text_vars: Optional[Set[str]] = None,
    rewrite_casts: bool = False,
) -> Tuple[str, List[str]]:
    """
    Core VB.NET -> Robin condition translator.
    When rewrite_casts=True, converts explicit numeric casts and numeric
    comparisons on known text variables to `<var>_Num` and returns the ordered
    list of variables requiring Text.ToNumber conversion.
    """
    if not raw_cond:
        return "True", []

    cond = clean_uipath_expression(raw_cond)
    cast_vars: List[str] = []

    def repl_cast(m: re.Match) -> str:
        var_name = m.group(1)
        if not rewrite_casts:
            return var_name
        if var_name not in cast_vars:
            cast_vars.append(var_name)
        return f"{var_name}_Num"

    cond = _NUMERIC_CAST_RE.sub(repl_cast, cond)

    # Handle .Equals("val", StringComparison...)
    equals_match = re.search(r'([a-zA-Z0-9_]+)(?:\.ToString)?(?:\.Trim)?\.Equals\s*\(\s*"([^"]+)"[^)]*\)', cond)
    if equals_match:
        var_n = equals_match.group(1)
        val_n = equals_match.group(2)
        cond = cond.replace(equals_match.group(0), f"{var_n} = $'''{val_n}'''")

    # Replace String.IsNullOrEmpty(var)
    null_match = re.search(r'String\.IsNullOrEmpty\s*\(\s*([a-zA-Z0-9_]+)\s*\)', cond)
    if null_match:
        var_name = null_match.group(1)
        cond = cond.replace(null_match.group(0), f"{var_name} = $''''''")

    # Replace VB logical operators with PAD operators
    cond = re.sub(r'\bAndAlso\b', 'AND', cond, flags=re.IGNORECASE)
    cond = re.sub(r'\bOrElse\b', 'OR', cond, flags=re.IGNORECASE)
    cond = re.sub(r'\bAnd\b', 'AND', cond, flags=re.IGNORECASE)
    cond = re.sub(r'\bOr\b', 'OR', cond, flags=re.IGNORECASE)
    cond = re.sub(r'\bNot\b', 'NOT', cond, flags=re.IGNORECASE)

    # Replace equality comparison == with = (Robin uses =)
    cond = re.sub(r'\s*==\s*', ' = ', cond)

    # Replace empty string "" with $''''''
    cond = cond.replace('""', "$''''''")

    # Replace string literals "text" with $'''text'''
    def repl_str(m: re.Match) -> str:
        return f"$'''{m.group(1)}'''"

    cond = re.sub(r'"([^"]*)"', repl_str, cond)

    if rewrite_casts and text_vars:
        # Mask Robin string literals before scanning for numeric comparisons
        masked_literals: List[str] = []

        def mask_lit(m: re.Match) -> str:
            idx = len(masked_literals)
            masked_literals.append(m.group(0))
            return f"__ROBIN_LIT_{idx}__"

        masked_cond = re.sub(r"\$'''.*?'''", mask_lit, cond)
        for v in sorted(text_vars):
            esc = re.escape(v)
            lhs_pat = re.compile(rf'\b{esc}(\s*(?:>=|<=|>|<)\s*-?\d+(?:\.\d+)?)\b')
            rhs_pat = re.compile(rf'(\b-?\d+(?:\.\d+)?\s*(?:>=|<=|>|<)\s*){esc}\b')
            new_masked, n1 = lhs_pat.subn(rf'{v}_Num\1', masked_cond)
            new_masked, n2 = rhs_pat.subn(rf'\g<1>{v}_Num', new_masked)
            if (n1 + n2) > 0:
                if v not in cast_vars:
                    cast_vars.append(v)
                masked_cond = new_masked

        for idx, lit in enumerate(masked_literals):
            masked_cond = masked_cond.replace(f"__ROBIN_LIT_{idx}__", lit)
        cond = masked_cond

    return cond.strip(), cast_vars


def convert_uipath_condition_to_robin(raw_cond: str) -> str:
    """
    Convert a UiPath condition expression (VB.NET) to Robin IF condition syntax.
    """
    cond, _ = _convert_condition_core(raw_cond, text_vars=None, rewrite_casts=False)
    return cond


def convert_uipath_condition_with_casts(
    raw_cond: str,
    text_vars: Optional[Set[str]] = None,
) -> Tuple[str, List[str]]:
    """
    Convert a UiPath condition expression to Robin IF condition syntax and return
    (robin_condition, vars_needing_text_to_number).
    """
    return _convert_condition_core(raw_cond, text_vars=text_vars, rewrite_casts=True)
