import os
import sys
import glob
import json
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

# Ensure parent directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from converter.project_manager import ProjectManager
from converter.models import ParsedActivity, WorkflowFile, ProjectMetadata

def clean_tag(tag: str) -> str:
    return tag.split('}')[-1] if '}' in tag else tag

class TrainingDatasetBuilder:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.pm = ProjectManager(include_comments=True, include_selectors_header=True)
        self.training_pairs: List[Dict[str, Any]] = []

    def build_all(self, output_dir: str = "data") -> Dict[str, Any]:
        """Extract paired training examples from all packages in data_dir."""
        packages = sorted(glob.glob(os.path.join(self.data_dir, "*.nupkg")) + glob.glob(os.path.join(self.data_dir, "*.zip")))
        all_projects = []
        total_activities = 0
        total_mapped = 0

        for pkg in packages:
            with open(pkg, "rb") as f:
                proj = self.pm.process_zip_bytes(f.read())
            all_projects.append(proj)
            total_activities += proj.total_activities
            total_mapped += proj.total_mapped

            # Extract activity-level pairs
            for wf in proj.workflows:
                for act in wf.all_activities:
                    if act.robin_code and act.is_mapped:
                        pair = {
                            "id": f"{proj.name}_{wf.filename}_{act.id}",
                            "bot_name": proj.name,
                            "workflow_file": wf.filename,
                            "activity_type": act.type_name,
                            "display_name": act.display_name,
                            "properties": {k: v for k, v in act.properties.items() if not k.startswith("_")},
                            "robin_script": act.robin_code.strip()
                        }
                        self.training_pairs.append(pair)

            # Extract full workflow pair
            for wf in proj.workflows:
                if wf.robin_script:
                    self.training_pairs.append({
                        "id": f"{proj.name}_{wf.filename}_full_workflow",
                        "bot_name": proj.name,
                        "workflow_file": wf.filename,
                        "activity_type": "FullWorkflow",
                        "display_name": wf.display_name,
                        "properties": {"filename": wf.filename, "variables_count": len(wf.variables)},
                        "robin_script": wf.robin_script.strip()
                    })

        # Save Alpaca-style instruction fine-tuning JSON
        alpaca_records = []
        openai_records = []

        for p in self.training_pairs:
            act_type = p["activity_type"]
            props_str = json.dumps(p["properties"], indent=2)
            prompt = f"Convert the following UiPath activity into Power Automate Desktop (Robin) script:\nActivity Type: {act_type}\nDisplay Name: {p['display_name']}\nProperties:\n{props_str}"
            response = p["robin_script"]

            alpaca_records.append({
                "instruction": f"Convert UiPath {act_type} activity to Power Automate Desktop (Robin) script.",
                "input": f"Activity: {p['display_name']}\nProperties: {props_str}",
                "output": response
            })

            openai_records.append({
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert RPA compiler that converts UiPath XAML activities and workflows into Microsoft Power Automate Desktop (Robin) scripts."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    },
                    {
                        "role": "assistant",
                        "content": response
                    }
                ]
            })

        # Write files
        os.makedirs(output_dir, exist_ok=True)
        pairs_path = os.path.join(output_dir, "training_pairs.json")
        alpaca_path = os.path.join(output_dir, "training_dataset_alpaca.json")
        openai_path = os.path.join(output_dir, "training_dataset_openai.jsonl")

        with open(pairs_path, "w", encoding="utf-8") as f:
            json.dump(self.training_pairs, f, indent=2)

        with open(alpaca_path, "w", encoding="utf-8") as f:
            json.dump(alpaca_records, f, indent=2)

        with open(openai_path, "w", encoding="utf-8") as f:
            for item in openai_records:
                f.write(json.dumps(item) + "\n")

        stats = {
            "total_packages": len(packages),
            "packages_analyzed": [os.path.basename(p) for p in packages],
            "total_activities_found": total_activities,
            "total_activities_mapped": total_mapped,
            "success_rate_percent": round((total_mapped / max(1, total_activities)) * 100, 2),
            "total_training_pairs": len(self.training_pairs),
            "output_files": [pairs_path, alpaca_path, openai_path]
        }

        stats_path = os.path.join(output_dir, "training_stats.json")
        with open(stats_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)

        return stats

if __name__ == "__main__":
    builder = TrainingDatasetBuilder()
    stats = builder.build_all()
    print("=" * 60)
    print("TRAINING DATASET GENERATION COMPLETE")
    print(json.dumps(stats, indent=2))
