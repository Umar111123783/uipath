from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

@dataclass
class ParsedVariable:
    name: str
    type_name: str
    default_value: Optional[str] = None
    scope: str = "Global"

@dataclass
class ParsedArgument:
    name: str
    direction: str  # In, Out, InOut
    type_name: str
    default_value: Optional[str] = None

@dataclass
class ParsedSelector:
    id: str
    name: str
    uipath_raw: str
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    tag: Optional[str] = None
    xpath: Optional[str] = None
    css: Optional[str] = None
    attributes: Dict[str, str] = field(default_factory=dict)
    control_code: str = ""

@dataclass
class ParsedActivity:
    id: str
    type_name: str
    display_name: str
    properties: Dict[str, Any] = field(default_factory=dict)
    children: List['ParsedActivity'] = field(default_factory=list)
    selectors: List[ParsedSelector] = field(default_factory=list)
    is_mapped: bool = False
    robin_code: str = ""
    notes: Optional[str] = None
    level: int = 0

@dataclass
class WorkflowFile:
    filename: str
    rel_path: str
    display_name: str
    is_main: bool = False
    raw_xaml: str = ""
    variables: List[ParsedVariable] = field(default_factory=list)
    arguments: List[ParsedArgument] = field(default_factory=list)
    root_activity: Optional[ParsedActivity] = None
    all_activities: List[ParsedActivity] = field(default_factory=list)
    selectors: List[ParsedSelector] = field(default_factory=list)
    robin_script: str = ""
    subflow_robin: str = ""
    mapped_count: int = 0
    unmapped_count: int = 0

@dataclass
class ProjectMetadata:
    name: str = "UiPathBot"
    description: str = ""
    main_file: str = "Main.xaml"
    schema_version: str = "4.0"
    target_framework: str = "Windows"
    dependencies: Dict[str, str] = field(default_factory=dict)
    workflows: List[WorkflowFile] = field(default_factory=list)
    total_activities: int = 0
    total_mapped: int = 0
    total_unmapped: int = 0
    all_selectors: List[ParsedSelector] = field(default_factory=list)

