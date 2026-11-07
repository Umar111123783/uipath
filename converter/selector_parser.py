import re
import html
from typing import Dict, List, Optional
from .models import ParsedSelector

def clean_selector_string(raw: str) -> str:
    """Unescape XML entities and strip quotes/whitespace."""
    if not raw:
        return ""
    s = raw.strip()
    s = html.unescape(s)
    # If wrapped in quotes or brackets
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1]
    return s

def parse_uipath_nodes(selector_str: str) -> List[Dict[str, str]]:
    """Parse XML nodes inside UiPath selector string."""
    cleaned = clean_selector_string(selector_str)
    # Matches tags like <webctrl tag='input' id='q' /> or <html ...>
    node_pattern = re.compile(r'<([a-zA-Z0-9_\-]+)([^>]*?)/?>')
    attr_pattern = re.compile(r'([a-zA-Z0-9_\-]+)\s*=\s*[\'"]([^\'"]*)[\'"]')
    
    nodes = []
    for match in node_pattern.finditer(cleaned):
        node_type = match.group(1).lower()
        attr_text = match.group(2)
        attrs = {}
        for attr_match in attr_pattern.finditer(attr_text):
            attrs[attr_match.group(1).lower()] = attr_match.group(2)
        nodes.append({
            "node_type": node_type,
            "attrs": attrs
        })
    return nodes

def convert_to_xpath(nodes: List[Dict[str, str]]) -> str:
    """Generate an XPath expression from parsed UiPath selector nodes."""
    if not nodes:
        return ""
    
    parts = []
    for node in nodes:
        node_type = node.get("node_type", "")
        attrs = node.get("attrs", {})
        
        # Skip top level window/html nodes if webctrl follows
        if node_type in ["html", "wnd"] and len(nodes) > 1:
            continue
            
        tag = attrs.get("tag", "*").lower()
        predicates = []
        
        if "id" in attrs:
            predicates.append(f"@id='{attrs['id']}'")
        if "name" in attrs:
            predicates.append(f"@name='{attrs['name']}'")
        if "class" in attrs:
            predicates.append(f"contains(@class, '{attrs['class']}')")
        if "type" in attrs:
            predicates.append(f"@type='{attrs['type']}'")
        if "aaname" in attrs:
            predicates.append(f"normalize-space(text())='{attrs['aaname']}'")
        elif "innertext" in attrs:
            predicates.append(f"contains(text(), '{attrs['innertext']}')")
        if "automationid" in attrs:
            predicates.append(f"@automationid='{attrs['automationid']}'")
        
        # If no standard attributes found, take other attributes
        if not predicates:
            for k, v in attrs.items():
                if k not in ["tag", "idx"]:
                    predicates.append(f"@{k}='{v}'")
                    
        pred_str = ("[" + " and ".join(predicates) + "]") if predicates else ""
        
        idx = attrs.get("idx")
        if idx and idx.isdigit():
            pred_str += f"[{idx}]"
            
        parts.append(f"{tag}{pred_str}")
        
    if not parts:
        return "//*"
    return "//" + "/".join(parts)

def convert_to_css(nodes: List[Dict[str, str]]) -> str:
    """Generate a CSS selector expression from parsed UiPath selector nodes."""
    if not nodes:
        return ""
    
    parts = []
    for node in nodes:
        node_type = node.get("node_type", "")
        attrs = node.get("attrs", {})
        
        if node_type in ["html", "wnd"] and len(nodes) > 1:
            continue
            
        tag = attrs.get("tag", "").lower()
        if not tag:
            tag = ""
            
        css_part = tag
        if "id" in attrs:
            css_part += f"#{attrs['id']}"
        elif "name" in attrs:
            css_part += f"[name='{attrs['name']}']"
        elif "class" in attrs:
            classes = attrs['class'].split()
            css_part += "".join(f".{c}" for c in classes if c)
            
        if "type" in attrs and "id" not in attrs:
            css_part += f"[type='{attrs['type']}']"
            
        if css_part:
            parts.append(css_part)
            
    return " > ".join(parts) if parts else "*"

def build_parsed_selector(raw_selector: str, index: int = 1, hint: str = "") -> ParsedSelector:
    """Construct a full ParsedSelector model from raw selector string."""
    cleaned = clean_selector_string(raw_selector)
    nodes = parse_uipath_nodes(cleaned)
    
    app_name = None
    window_title = None
    tag = None
    all_attrs = {}
    
    for node in nodes:
        attrs = node.get("attrs", {})
        all_attrs.update(attrs)
        if "app" in attrs:
            app_name = attrs["app"]
        if "title" in attrs:
            window_title = attrs["title"]
        if "tag" in attrs and not tag:
            tag = attrs["tag"]
            
    xpath = convert_to_xpath(nodes)
    css = convert_to_css(nodes)
    
    # Generate clean name for Power Automate control
    safe_hint = re.sub(r'[^a-zA-Z0-9_]', '_', hint).strip('_') if hint else ""
    if not safe_hint:
        attr_name = all_attrs.get("id") or all_attrs.get("name") or all_attrs.get("aaname") or tag or "Element"
        safe_hint = re.sub(r'[^a-zA-Z0-9_]', '_', attr_name).strip('_')
        
    safe_name = f"UI_{safe_hint}_{index}"
    sel_id = f"sel_{index}"
    control_code = f"appmask['{safe_name}']"
    
    return ParsedSelector(
        id=sel_id,
        name=safe_name,
        uipath_raw=cleaned,
        app_name=app_name,
        window_title=window_title,
        tag=tag,
        xpath=xpath,
        css=css,
        attributes=all_attrs,
        control_code=control_code
    )

