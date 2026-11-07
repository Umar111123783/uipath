import os
import shutil
import zipfile
import tempfile
from pathlib import Path
from typing import List, Union, Any

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
