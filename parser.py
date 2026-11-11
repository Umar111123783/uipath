import hashlib
import json
import os
import re
import shutil
import zipfile
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

def extract_zip(uploaded: Any) -> str:
    """
    Extracts an uploaded .zip or .nupkg file (or file path/BytesIO) to a directory
    and returns the folder path.
    """
    extract_base = Path("extracted_projects")
    extract_base.mkdir(exist_ok=True)
    
    # Determine a clean project name
    if hasattr(uploaded, "name"):
        base_name = Path(uploaded.name).stem
        if base_name.endswith(".nupkg") or base_name.endswith(".zip"):
            base_name = Path(base_name).stem
    elif isinstance(uploaded, (str, Path)):
        base_name = Path(uploaded).stem
    else:
        base_name = "uipath_project"
        
    target_folder = extract_base / base_name
    if target_folder.exists():
        shutil.rmtree(target_folder, ignore_errors=True)
    target_folder.mkdir(parents=True, exist_ok=True)
    
    # Extract
    if hasattr(uploaded, "read"):
        # Reset pointer if seekable
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)
        with zipfile.ZipFile(uploaded, "r") as z:
            z.extractall(target_folder)
    else:
        with zipfile.ZipFile(uploaded, "r") as z:
            z.extractall(target_folder)
            
    return str(target_folder.resolve())

def get_xaml_files(project_folder: Union[str, Path]) -> List[str]:
    """Return all .xaml files found in the project folder."""
    folder = Path(project_folder)
    xaml_files = list(folder.rglob("*.xaml"))
    # Filter out macOS artifacts
    xaml_files = [str(f) for f in xaml_files if not f.name.startswith("._") and "__MACOSX" not in str(f)]
    # Sort with Main.xaml first
    xaml_files.sort(key=lambda x: (0 if "main.xaml" in Path(x).name.lower() else 1, x))
    return xaml_files

def get_dll_files(project_folder: Union[str, Path]) -> List[str]:
    """Return all .dll files found in the project folder."""
    folder = Path(project_folder)
    dlls = list(folder.rglob("*.dll"))
    return [f.name for f in dlls if not f.name.startswith("._")]

def get_important_files(project_folder: Union[str, Path]) -> List[str]:
    """Return key project files like project.json, nuspec, uiproj, uiform, etc."""
    folder = Path(project_folder)
    important_patterns = ["project.json", "*.nuspec", "*.uiproj", "*.uiform", "*.xlsx", "*.txt", "*.json"]
    found = set()
    for pat in important_patterns:
        for f in folder.rglob(pat):
            rel = str(f.relative_to(folder))
            parts = [p.lower() for p in f.parts]
            if ".settings" in parts or ".project" in parts or "_rels" in parts or "__macosx" in parts or f.name.startswith("._"):
                continue
            # Filter noise json
            if f.name.endswith(".json") and f.name not in ["project.json", "operate.json", "package-descriptor.json", "FormsRuntime.json"]:
                continue
            found.add(rel)
    return sorted(list(found))

def get_project_tree(project_folder: Union[str, Path], max_depth: int = 4) -> str:
    """Generate a clean ASCII tree representation of the project structure."""
    folder = Path(project_folder)
    lines = [f"📦 {folder.name}/"]
    
    def walk_dir(current_dir: Path, prefix: str = "", depth: int = 0):
        if depth >= max_depth:
            return
        try:
            entries = sorted(list(current_dir.iterdir()), key=lambda p: (0 if p.is_dir() else 1, p.name.lower()))
            # Filter internal/hidden noise
            entries = [e for e in entries if not e.name.startswith(".") and not e.name.startswith("._") and e.name != "__MACOSX"]
        except Exception:
            return
            
        total = len(entries)
        for i, entry in enumerate(entries):
            is_last = (i == total - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")
            
            if entry.is_dir():
                lines.append(f"{prefix}{connector}📁 {entry.name}/")
                walk_dir(entry, child_prefix, depth + 1)
            else:
                icon = "📄"
                if entry.suffix.lower() == ".xaml":
                    icon = "⚡"
                elif entry.suffix.lower() == ".dll":
                    icon = "⚙️"
                elif entry.suffix.lower() == ".json":
                    icon = "🔧"
                elif entry.suffix.lower() in [".xlsx", ".xls"]:
                    icon = "📊"
                lines.append(f"{prefix}{connector}{icon} {entry.name}")
                
    walk_dir(folder, "", 0)
    return "\n".join(lines)

def build_xml_context(project_folder: Union[str, Path]) -> str:
    """
    Build a comprehensive context string combining all XAML files, project.json,
    and metadata for the LLM.
    """
    folder = Path(project_folder)
    context_parts = []
    
    # 1. Project metadata if exists
    for proj_json in folder.rglob("project.json"):
        if not proj_json.name.startswith("._"):
            try:
                rel = proj_json.relative_to(folder)
                context_parts.append(f"{'='*80}\nFILE: {rel}\n{'='*80}")
                context_parts.append(proj_json.read_text(encoding="utf-8", errors="ignore"))
                context_parts.append("\n")
            except Exception:
                pass
                
    # 2. All XAML files
    xaml_files = get_xaml_files(folder)
    for xf in xaml_files:
        try:
            x_path = Path(xf)
            rel = x_path.relative_to(folder)
            context_parts.append(f"{'='*80}\nWORKFLOW XAML FILE: {rel}\n{'='*80}")
            context_parts.append(x_path.read_text(encoding="utf-8", errors="ignore"))
            context_parts.append("\n")
        except Exception as e:
            context_parts.append(f"# Error reading {xf}: {str(e)}\n")
            
    return "\n".join(context_parts)


_NODE_ID_LINE_PATTERN = re.compile(r'^\s*#\s*node_id\s*=', re.IGNORECASE)

_ROBIN_STRIP_LINE_PATTERNS = [
    re.compile(r'^\s*#\s*[=\-\*_]{4,}.*$'),
    re.compile(r'^\s*#\s*POWER AUTOMATE DESKTOP\b', re.IGNORECASE),
    re.compile(r'^\s*#\s*(?:Project|Total Workflows|Total Activities|Conversion Success Rate|Instructions)\s*:', re.IGNORECASE),
    re.compile(r'^\s*#\s*Power Automate Desktop flow designer canvas\.?\s*$', re.IGNORECASE),
    re.compile(r'^\s*#\s*Converted from UiPath Workflow\s*:', re.IGNORECASE),
    re.compile(r'^\s*#\s*(?:Arguments|Variables)\s*\(\d+\)\s*:', re.IGNORECASE),
    re.compile(r'^\s*#\s*-\s*(?:\[[^\]]+\]\s*)?%[a-zA-Z0-9_]+%\s*\(', re.IGNORECASE),
    re.compile(r'^\s*#\s*\*+\s*TASK NAME\s*:', re.IGNORECASE),
    re.compile(r'^\s*#\s*---\s*.*?\s*---\s*$'),
    re.compile(r'^\s*#\s*\[ControlRepositoryFolder\]\s*$', re.IGNORECASE),
    re.compile(r'^\s*#\s*(?:Control|XPath|CSS|UiPath)\s*:', re.IGNORECASE),
]


_HTML_ENTITY_REPLACEMENTS = (
    ("&gt;", ">"),
    ("&lt;", "<"),
    ("&quot;", '"'),
    ("&#39;", "'"),
    ("&apos;", "'"),
    ("&nbsp;", " "),
    ("&amp;", "&"),
)


def _decode_numeric_entity(match: re.Match, base: int) -> str:
    try:
        code_point = int(match.group(1), base)
        if 0 <= code_point <= 0x10FFFF:
            return chr(code_point)
    except ValueError:
        pass
    return match.group(0)


def _decode_html_entities(text: str) -> str:
    """Decode HTML character entities (including double-encoded sequences) into plain text."""
    prev = None
    cur = text
    for _ in range(3):
        if cur == prev:
            break
        prev = cur
        for entity, repl in _HTML_ENTITY_REPLACEMENTS:
            cur = re.sub(re.escape(entity), repl, cur, flags=re.IGNORECASE)
        cur = re.sub(r'&#(\d+);', lambda m: _decode_numeric_entity(m, 10), cur)
        cur = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: _decode_numeric_entity(m, 16), cur)
    return cur


def _clean_html_corruption(text: str) -> str:
    """Strip HTML <br> tags, anchor tags (<a href=...>), NBSPs, autolinks, and HTML entities."""
    cleaned = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    cleaned = re.sub(r'<a\b[^>]*>(.*?)</a>', r'\1', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = _decode_html_entities(cleaned)
    cleaned = cleaned.replace('\u00a0', ' ')
    cleaned = re.sub(r'<br\s*/?>', '\n', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'<a\b[^>]*>(.*?)</a>', r'\1', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'\[(https?://[^\]]+)\]\(\1\)', r'\1', cleaned)
    cleaned = re.sub(r'<(https?://[^>\s]+)>', r'\1', cleaned)
    return cleaned


def sanitize_robin_script(
    script: str,
    keep_node_metadata: bool = False,
    preserve_blank_lines: bool = False,
) -> str:
    """
    Clean HTML entities/anchor tags, metadata banners, decorative dividers,
    trailing inline # XPath comments, and optionally # node_id metadata or blank lines.
    """
    if not script:
        return ""

    script = _clean_html_corruption(script)
    cleaned_lines: List[str] = []
    in_control_repo = False
    for raw_line in script.splitlines():
        if not raw_line.strip():
            if preserve_blank_lines and cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        if re.match(r'^\s*#\s*\[ControlRepositoryFolder\]\s*$', raw_line, re.IGNORECASE):
            in_control_repo = True
            continue
        if in_control_repo:
            if re.match(r'^\s*#\s*End\s+ControlRepositoryFolder\b', raw_line, re.IGNORECASE):
                in_control_repo = False
                continue
            if raw_line.lstrip().startswith("#"):
                continue
            in_control_repo = False

        if not keep_node_metadata and _NODE_ID_LINE_PATTERN.match(raw_line):
            continue

        # Drop header / metadata / decorative divider lines
        if any(pat.match(raw_line) for pat in _ROBIN_STRIP_LINE_PATTERNS):
            continue

        # Strip trailing inline XPath comment from action statements
        line = re.sub(r'\s+#\s*XPath:\s*.*$', '', raw_line).rstrip()
        if not line.strip():
            continue

        cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    return "\n".join(cleaned_lines)


# Table-driven mapping from Robin statement prefixes to (package, action, resolved)
_ROBIN_LINE_METADATA: Tuple[Tuple[str, Tuple[str, str, str]], ...] = (
    ("Display.InputDialog", ("Display", "inputDialog", "input dialog")),
    ("Display.ShowMessageDialog", ("MessageBox", "messageBox", "show message")),
    ("Text.ToNumber", ("Text", "toNumber", "convert text to number")),
    ("Wait ", ("Delay", "delay", "delay")),
    ("WAIT ", ("Delay", "delay", "delay")),
    ("Web.InvokeWebService", ("Web", "invokeWebService", "invoke web service")),
    ("Variables.ConvertJsonToCustomObject", ("Json", "deserializeJson", "convert json to custom object")),
    ("Variables.CreateNewList", ("List", "createNewList", "create new list")),
    ("Variables.CreateNewDatatable", ("DataTable", "buildDataTable", "create new datatable")),
    ("Variables.AddRowToDataTable", ("DataTable", "addDataRow", "add row to datatable")),
    ("Folder.GetSpecialFolder", ("Folder", "getSpecialFolder", "get special folder")),
    ("Folder.Create", ("Folder", "createFolder", "create folder")),
    ("File.ReadTextFile", ("File", "readTextFile", "read text file")),
    ("File.ReadText", ("File", "readTextFile", "read text file")),
    ("File.WriteText", ("File", "writeTextFile", "write text file")),
    ("File.Copy", ("File", "copyFiles", "copy files")),
    ("File.Move", ("File", "moveFiles", "move files")),
    ("File.Delete", ("File", "deleteFiles", "delete files")),
    ("Excel.LaunchExcel", ("Excel", "excelScope", "launch excel")),
    ("Excel.SetActiveWorksheet", ("Excel", "setActiveWorksheet", "set active worksheet")),
    ("Excel.ReadFromExcel", ("Excel", "readRange", "read excel range")),
    ("Excel.WriteToExcel", ("Excel", "writeCell", "write to excel")),
    ("Excel.SaveExcel", ("Excel", "saveExcel", "save excel")),
    ("Excel.CloseExcel", ("Excel", "closeExcel", "close excel")),
    ("WebAutomation.Launch", ("WebAutomation", "openBrowser", "launch browser")),
    ("WebAutomation.CloseWebBrowser", ("WebAutomation", "closeBrowser", "close browser")),
    ("WebAutomation.Navigate", ("WebAutomation", "navigate", "navigate")),
    ("WebAutomation.Click", ("WebAutomation", "click", "click")),
    ("WebAutomation.FormFilling", ("WebAutomation", "typeInto", "populate text field")),
    ("WebAutomation.DataExtraction", ("WebAutomation", "getValue", "get text")),
    ("MouseAndKeyboard.SendKeys", ("MouseAndKeyboard", "sendKeys", "send keys")),
    ("System.RunApplication", ("System", "runApplication", "run application")),
    ("System.TerminateProcess", ("System", "terminateProcess", "terminate process")),
    ("Flow.RunFlow", ("FlowControl", "runSubflow", "run subflow")),
    ("CALL ", ("FlowControl", "runSubflow", "run subflow")),
    ("EXIT Code", ("FlowControl", "stopFlow", "stop flow")),
    ("FlowControl.StopFlow", ("FlowControl", "stopFlow", "stop flow")),
    ("IF ", ("If", "if", "if")),
    ("IF (", ("If", "if", "if")),
    ("ELSE IF ", ("If", "elseIf", "else if")),
    ("ELSE", ("If", "else", "else")),
    ("SWITCH ", ("Switch", "switch", "switch")),
    ("CASE ", ("Switch", "case", "case")),
    ("DEFAULT", ("Switch", "default", "default")),
    ("LOOP FOREACH ", ("Loop", "loop", "loop foreach")),
    ("LOOP WHILE ", ("Loop", "loop", "loop while")),
    ("LOOP ", ("Loop", "loop", "loop")),
    ("EXIT LOOP", ("Loop", "exitLoop", "exit loop")),
    ("EXIT", ("FlowControl", "stopFlow", "stop flow")),
    ("NEXT LOOP", ("Loop", "nextLoop", "next loop")),
    ("ON BLOCK ERROR", ("ErrorHandling", "onError", "on block error")),
    ("# [Log", ("Log", "logMessage", "log message")),
    ("# [Console Log", ("Log", "writeLine", "write line")),
    ("# ", ("Comment", "Comment", "comment")),
)

_BLOCK_OPENER_RE = re.compile(
    r'^(?:IF\b.*\bTHEN|ELSE\s+IF\b.*\bTHEN|ELSE|SWITCH\b.*|CASE\b.*|DEFAULT|LOOP\b.*|FUNCTION\b.*|ON BLOCK ERROR.*)$'
)
_BLOCK_END_LINES = {"END", "END FUNCTION", "END SWITCH", "END ON BLOCK ERROR"}


def infer_assign_metadata(
    var_name: str, val_expr: str, explicit_type: str = ""
) -> Tuple[str, str, str]:
    """Infer (package, action, resolved) metadata for a variable assignment."""
    vtype = explicit_type.lower()
    if any(tok in vtype for tok in ("int", "num", "double", "decimal", "single")):
        return ("Number", "assignToNumber", "assign")
    if "bool" in vtype:
        return ("Boolean", "assign", "assign")
    if "list" in vtype or "array" in vtype:
        return ("List", "assign", "assign")
    if "datatable" in vtype:
        return ("DataTable", "assign", "assign")
    if "jobject" in vtype or "customobject" in vtype:
        return ("CustomObject", "assign", "assign")

    rhs = val_expr.strip()
    if rhs in ("True", "False"):
        return ("Boolean", "assign", "assign")
    if re.match(r'^-?\d+(?:\.\d+)?$', rhs) or ".Count%" in rhs or ".Length%" in rhs:
        return ("Number", "assignToNumber", "assign")

    name_lower = var_name.lower()
    rhs_lower = rhs.lower()
    if (
        "filepath" in name_lower
        or "excelpath" in name_lower
        or any(ext in rhs_lower for ext in (".xlsx", ".xls", ".csv", ".txt", ".pdf", ".json", ".xml"))
    ):
        return ("File", "assign", "assign")

    return ("String", "assign", "assign")


def classify_robin_line(
    stripped_line: str, var_types: Optional[Dict[str, str]] = None
) -> Optional[Tuple[str, str, str]]:
    """Return (package, action, resolved) for executable lines, or None for END/FUNCTION closers."""
    if stripped_line in _BLOCK_END_LINES or stripped_line.startswith("FUNCTION "):
        return None
    if stripped_line.startswith("# node_id="):
        return None

    set_match = re.match(r'^SET\s+([a-zA-Z0-9_]+)\s+TO\s+(.+)$', stripped_line)
    if set_match:
        var_name, rhs = set_match.group(1), set_match.group(2)
        explicit = var_types.get(var_name, "") if var_types else ""
        return infer_assign_metadata(var_name, rhs, explicit)

    for prefix, meta in _ROBIN_LINE_METADATA:
        if stripped_line.startswith(prefix):
            return meta

    return ("Core", "action", "action")


def format_node_comment(
    workflow_name: str, counter: int, package: str, action: str, resolved: str
) -> str:
    """Create a structured `# node_id=...` comment matching PAD/AA node syntax."""
    seed = f"{workflow_name}_{counter:05d}_{package}_{action}"
    hex8 = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
    return f"# node_id={workflow_name}.{counter:05d}.{hex8}; package={package}; action={action}; resolved={resolved}"


def extract_robin_metadata_context(xml_context: str) -> Tuple[str, Dict[str, str]]:
    """Extract sanitized project/workflow name and XAML variable type map from XML context."""
    workflow_name = "Workflow"
    var_types: Dict[str, str] = {}

    if not xml_context:
        return workflow_name, var_types

    # 1. Try project.json "name" field first
    proj_match = re.search(
        r'FILE:\s*[^\n]*project\.json[^\n]*\n=+\n(.*?)(?:\n=+|\Z)',
        xml_context,
        re.DOTALL | re.IGNORECASE,
    )
    if proj_match:
        try:
            proj_data = json.loads(proj_match.group(1).strip())
            if isinstance(proj_data, dict) and proj_data.get("name"):
                workflow_name = re.sub(r'[^a-zA-Z0-9_]', '_', str(proj_data["name"])) or workflow_name
        except Exception:
            pass

    # Fallback: use first workflow XAML filename stem
    if workflow_name == "Workflow":
        wf_match = re.search(r'WORKFLOW XAML FILE:\s*([^\r\n]+)', xml_context, re.IGNORECASE)
        if wf_match:
            stem = Path(wf_match.group(1).strip()).stem
            workflow_name = re.sub(r'[^a-zA-Z0-9_]', '_', stem) or workflow_name

    # 2. Extract XAML variable declarations (<Variable x:TypeArguments="..." Name="..." />)
    for tag_match in re.finditer(r'<Variable\b([^>]+)>', xml_context):
        attrs = tag_match.group(1)
        name_m = re.search(r'\bName\s*=\s*"([^"]+)"', attrs)
        type_m = re.search(r'\bx:TypeArguments\s*=\s*"([^"]+)"', attrs)
        if name_m and type_m:
            var_types[name_m.group(1)] = type_m.group(1)

    return workflow_name, var_types


def apply_robin_node_metadata(
    script: str,
    workflow_name: str = "Workflow",
    var_types: Optional[Dict[str, str]] = None,
    reset_per_subflow: bool = False,
) -> str:
    """Annotate every executable Robin line with `# node_id=<Flow>.<idx>.<hex8>; ...`."""
    if not script:
        return script

    active_flow = re.sub(r'[^a-zA-Z0-9_]', '_', workflow_name or "Workflow") or "Workflow"
    base_flow = active_flow
    counter = 1
    out_lines: List[str] = []

    for raw_line in script.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        if reset_per_subflow and stripped.startswith("FUNCTION "):
            func_name = re.sub(r'[^a-zA-Z0-9_]', '_', stripped[9:].strip().split("(")[0].strip()) or "Workflow"
            active_flow = base_flow if (func_name.lower() == "main" and base_flow != "Workflow") else func_name
            counter = 1
            if out_lines:
                out_lines.append("")
            out_lines.append(raw_line.rstrip())
            continue

        indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
        meta = classify_robin_line(stripped, var_types)
        if meta is None:
            out_lines.append(raw_line.rstrip())
            continue

        if out_lines:
            prev_stripped = out_lines[-1].strip()
            if not _BLOCK_OPENER_RE.match(prev_stripped):
                out_lines.append("")

        pkg, action, resolved = meta
        out_lines.append(f"{indent}{format_node_comment(active_flow, counter, pkg, action, resolved)}")
        counter += 1
        out_lines.append(raw_line.rstrip())

    return "\n".join(out_lines)
