import re
from typing import Tuple

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

    # Pre-clean common VB.NET idioms
    # Replace escaped quotes in VB: "" -> "
    vb_clean = expr.replace('""', '"')
    
    # Check if a single string literal with quotes: e.g. ["Hello World"]
    single_str_match = re.match(r'^"([^"]*)"$', vb_clean, re.DOTALL)
    if single_str_match:
        content = single_str_match.group(1)
        return f"$'''{content}'''"
        
    # Check if string interpolation $"Hello {name}"
    interp_match = re.match(r'^\$"([^"]*)"$', vb_clean, re.DOTALL)
    if interp_match:
        content = interp_match.group(1)
        replaced = re.sub(r'\{([a-zA-Z0-9_]+)\}', r'%\1%', content)
        return f"$'''{replaced}'''"

    # Check if simple variable identifier: e.g. [searchQuery]
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', expr):
        return f"%{expr}%"

    # Token access like jsonObj("title").ToString or currentJToken("body").ToString
    token_match = re.match(r'^([a-zA-Z0-9_]+)\("([^"]+)"\)(?:\.ToString(?:\(\))?)?$', expr)
    if token_match:
        var_obj = token_match.group(1)
        var_key = token_match.group(2)
        if var_obj == "currentJToken":
            return f"%CurrentItem['{var_key}']%"
        return f"%{var_obj}['{var_key}']%"

    # Check if string concatenation: "prefix " + var + " suffix" or & in VB
    # Handle split on + or & outside quotes
    parts = re.split(r'\s*[\+&]\s*', vb_clean)
    if len(parts) > 1:
        has_string_part = any(p.strip().startswith('"') and p.strip().endswith('"') for p in parts)
        if has_string_part or any("vbCrLf" in p or "NewLine" in p for p in parts):
            text_builder = []
            is_all_text_and_vars = True
            for p in parts:
                p_strip = p.strip()
                if p_strip in ["vbCrLf", "Environment.NewLine"]:
                    text_builder.append("\n")
                elif p_strip.startswith('"') and p_strip.endswith('"'):
                    text_builder.append(p_strip[1:-1])
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
                combined = "".join(text_builder)
                return f"$'''{combined}'''"

    # Arithmetic expression: rowCount + 1, x - 5, count * 2
    if re.match(r'^[a-zA-Z0-9_\s\+\-\*\/\(\)\.]+$', expr) and not any(k in expr for k in ["new ", "New "]):
        return f"%{expr}%"

    # For general expressions, wrap in %...% for PAD
    return f"%{expr}%"

def convert_uipath_condition_to_robin(raw_cond: str) -> str:
    """
    Convert a UiPath condition expression (VB.NET) to Robin IF condition syntax.
    VB.NET:
      x > 5 AndAlso y < 10
      CInt(userAgeText) >= 18
      rowStatus.ToString.Trim.Equals("Completed", StringComparison.OrdinalIgnoreCase)
      String.IsNullOrEmpty(employeeEmail)
    PAD Robin:
      x > 5 AND y < 10
      userAgeText >= 18
      rowStatus = $'''Completed'''
      employeeEmail = $''''''
    """
    if not raw_cond:
        return "True"
        
    cond = clean_uipath_expression(raw_cond)
    
    # Strip CInt(...) or Convert.ToInt32(...)
    cond = re.sub(r'\bCInt\s*\(\s*([a-zA-Z0-9_]+)\s*\)', r'\1', cond)
    cond = re.sub(r'\bConvert\.ToInt32\s*\(\s*([a-zA-Z0-9_]+)\s*\)', r'\1', cond)
    
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
    def repl_str(m):
        return f"$'''{m.group(1)}'''"
    cond = re.sub(r'"([^"]*)"', repl_str, cond)
    
    return cond.strip()
