import io
import json
import os
import zipfile
from typing import Dict, List, Optional, Tuple, Union
from .models import ProjectMetadata, WorkflowFile, ParsedSelector
from .uipath_parser import UiPathXamlParser
from .robin_generator import RobinGenerator

class ProjectManager:
    def __init__(self, include_comments: bool = True, include_selectors_header: bool = True):
        self.include_comments = include_comments
        self.include_selectors_header = include_selectors_header
        self.generator = RobinGenerator(
            include_comments=include_comments,
            include_selectors_header=include_selectors_header
        )

    def process_zip_bytes(self, zip_bytes: bytes, project_name_override: Optional[str] = None) -> ProjectMetadata:
        """Process an in-memory zip file of a UiPath project."""
        metadata = ProjectMetadata()
        workflows: List[WorkflowFile] = []
        all_selectors: List[ParsedSelector] = []
        
        with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as z:
            namelist = z.namelist()
            
            # 1. Look for project.json
            project_json_file = None
            for name in namelist:
                if name.lower().endswith("project.json"):
                    project_json_file = name
                    break
                    
            if project_json_file:
                try:
                    data = json.loads(z.read(project_json_file).decode('utf-8', errors='ignore'))
                    metadata.name = data.get("name", "UiPathProject")
                    metadata.description = data.get("description", "")
                    metadata.main_file = data.get("main", "Main.xaml")
                    metadata.schema_version = data.get("schemaVersion", "4.0")
                    metadata.target_framework = data.get("targetFramework", "Windows")
                    metadata.dependencies = data.get("dependencies", {})
                except Exception:
                    pass
            elif project_name_override:
                metadata.name = project_name_override

            # 2. Extract and parse all .xaml files
            xaml_files = [n for n in namelist if n.lower().endswith(".xaml") and not n.startswith("__MACOSX")]
            
            # Sort so Main.xaml comes first
            xaml_files.sort(key=lambda x: 0 if "main.xaml" in x.lower() else 1)
            
            for xaml_path in xaml_files:
                try:
                    raw_content = z.read(xaml_path).decode('utf-8', errors='ignore')
                    filename = os.path.basename(xaml_path)
                    parser = UiPathXamlParser(filename=filename, content=raw_content, rel_path=xaml_path)
                    wf = parser.parse()
                    
                    # Generate single-flow Robin script
                    self.generator.generate_for_workflow(wf, as_subflow=False)
                    self.generator.generate_for_workflow(wf, as_subflow=True)
                    
                    # Count activities
                    mapped = sum(1 for a in wf.all_activities if a.is_mapped)
                    unmapped = len(wf.all_activities) - mapped
                    wf.mapped_count = mapped
                    wf.unmapped_count = unmapped
                    
                    workflows.append(wf)
                    all_selectors.extend(wf.selectors)
                except Exception as e:
                    # Create error workflow placeholder
                    err_wf = WorkflowFile(
                        filename=os.path.basename(xaml_path),
                        rel_path=xaml_path,
                        display_name=os.path.basename(xaml_path).replace(".xaml", ""),
                        robin_script=f"# Error parsing {xaml_path}: {str(e)}"
                    )
                    workflows.append(err_wf)

        metadata.workflows = workflows
        metadata.all_selectors = all_selectors
        metadata.total_activities = sum(len(wf.all_activities) for wf in workflows)
        metadata.total_mapped = sum(wf.mapped_count for wf in workflows)
        metadata.total_unmapped = sum(wf.unmapped_count for wf in workflows)
        
        return metadata

    def process_single_xaml(self, xaml_content: str, filename: str = "Main.xaml") -> ProjectMetadata:
        """Process a single raw XAML string."""
        metadata = ProjectMetadata(
            name=filename.replace(".xaml", ""),
            main_file=filename
        )
        parser = UiPathXamlParser(filename=filename, content=xaml_content)
        wf = parser.parse()
        
        self.generator.generate_for_workflow(wf, as_subflow=False)
        self.generator.generate_for_workflow(wf, as_subflow=True)
        
        mapped = sum(1 for a in wf.all_activities if a.is_mapped)
        unmapped = len(wf.all_activities) - mapped
        wf.mapped_count = mapped
        wf.unmapped_count = unmapped
        
        metadata.workflows = [wf]
        metadata.all_selectors = wf.selectors
        metadata.total_activities = len(wf.all_activities)
        metadata.total_mapped = mapped
        metadata.total_unmapped = unmapped
        
        return metadata

    def get_full_project_robin(self, project: ProjectMetadata) -> str:
        """Get the combined PAD script with all subflows."""
        return self.generator.generate_full_project(project)

    def get_clean_pasteable_robin(self, project: ProjectMetadata) -> str:
        """Get the clean, guaranteed canvas pasteable PAD script (no headers, pure actions)."""
        return self.generator.generate_clean_pasteable_script(project)

