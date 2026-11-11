import xml.etree.ElementTree as ET
import re
from typing import List, Dict, Optional, Tuple, Any
from .models import (
    ParsedActivity, ParsedVariable, ParsedArgument, ParsedSelector, WorkflowFile
)
from .selector_parser import build_parsed_selector
from .expression_parser import clean_uipath_expression

def clean_tag(tag: str) -> str:
    """Strip XML namespace prefix from tag."""
    if '}' in tag:
        return tag.split('}', 1)[1]
    if ':' in tag:
        return tag.split(':', 1)[1]
    return tag

IGNORED_METADATA_TAGS = {
    "NamespacesForImplementation", "ReferencesForImplementation",
    "AssemblyReference", "ViewState", "ViewStateData", "Variables",
    "Members", "Property", "Member", "Collections", "Dictionary",
    "ActivityAction.Argument", "DelegateInArgument", "Boolean", "String",
    "Int32", "Literal", "HintSize", "Flowchart.StartNode", "WorkflowViewStateService.ViewState"
}

def is_metadata_or_prop_tag(tag: str) -> bool:
    if "ViewState" in tag:
        return True
    if tag in IGNORED_METADATA_TAGS:
        return True
    if tag in ["InArgument", "OutArgument", "InOutArgument", "Literal", "Dictionary", "Collection"]:
        return True
    return False

class UiPathXamlParser:
    def __init__(self, filename: str, content: str, rel_path: str = ""):
        self.filename = filename
        self.rel_path = rel_path or filename
        self.content = content
        self.variables: List[ParsedVariable] = []
        self.arguments: List[ParsedArgument] = []
        self.selectors: List[ParsedSelector] = []
        self.all_activities: List[ParsedActivity] = []
        self.selector_counter = 1
        self.activity_counter = 1
        
    def parse(self) -> WorkflowFile:
        try:
            root = ET.fromstring(self.content)
        except Exception as e:
            wf = WorkflowFile(
                filename=self.filename,
                rel_path=self.rel_path,
                display_name=self.filename.replace(".xaml", ""),
                is_main="main" in self.filename.lower(),
                raw_xaml=self.content
            )
            wf.robin_script = f"# Error parsing {self.filename}: {str(e)}"
            return wf

        self._parse_arguments(root)
        self._parse_variables(root)
        
        root_act = self._find_and_parse_root_activity(root)
        
        is_main = "main" in self.filename.lower()
        wf = WorkflowFile(
            filename=self.filename,
            rel_path=self.rel_path,
            display_name=self.filename.replace(".xaml", ""),
            is_main=is_main,
            raw_xaml=self.content,
            variables=self.variables,
            arguments=self.arguments,
            root_activity=root_act,
            all_activities=self.all_activities,
            selectors=self.selectors
        )
        return wf

    def _parse_arguments(self, root: ET.Element):
        """Parse x:Members / x:Property elements for in/out workflow arguments."""
        for elem in root.iter():
            tag = clean_tag(elem.tag)
            if tag in ["Property", "Member"] and "Name" in elem.attrib:
                name = elem.attrib.get("Name", "")
                prop_type = elem.attrib.get("Type", "x:String")
                direction = "In"
                if "OutArgument" in prop_type:
                    direction = "Out"
                elif "InOutArgument" in prop_type:
                    direction = "InOut"
                self.arguments.append(ParsedArgument(
                    name=name,
                    direction=direction,
                    type_name=prop_type
                ))

    def _parse_variables(self, root: ET.Element):
        """Parse Variable elements."""
        for elem in root.iter():
            tag = clean_tag(elem.tag)
            if tag == "Variable" and "Name" in elem.attrib:
                name = elem.attrib.get("Name", "")
                type_name = (
                    elem.attrib.get("TypeArguments")
                    or next(
                        (v for k, v in elem.attrib.items() if k.endswith("}TypeArguments") or k.endswith(":TypeArguments")),
                        "x:String"
                    )
                )
                clean_type = type_name.split(":")[-1]
                default_val = elem.attrib.get("Default")
                self.variables.append(ParsedVariable(
                    name=name,
                    type_name=clean_type,
                    default_value=default_val
                ))

    def _find_and_parse_root_activity(self, root: ET.Element) -> Optional[ParsedActivity]:
        """Find the main execution container: Sequence, Flowchart, StateMachine, or root."""
        for child in root:
            tag = clean_tag(child.tag)
            if tag in ["Sequence", "Flowchart", "StateMachine", "FlowStep", "ExcelProcessScopeX"]:
                return self._parse_activity_node(child, level=0)
                
        for elem in root.iter():
            tag = clean_tag(elem.tag)
            if tag in ["Sequence", "Flowchart"]:
                return self._parse_activity_node(elem, level=0)
                
        return None

    def _parse_activity_node(self, node: ET.Element, level: int = 0) -> ParsedActivity:
        """Recursively parse an activity node into a ParsedActivity."""
        tag = clean_tag(node.tag)
        disp_name = node.attrib.get("DisplayName", tag)
        act_id = f"act_{self.activity_counter}"
        self.activity_counter += 1
        
        props: Dict[str, Any] = dict(node.attrib)
        child_activities: List[ParsedActivity] = []
        node_selectors: List[ParsedSelector] = []
        
        for child in node:
            child_tag = clean_tag(child.tag)
            
            # Skip pure metadata or ViewState nodes
            if is_metadata_or_prop_tag(child_tag) and not child_tag.endswith(".Body") and not child_tag.endswith(".Then") and not child_tag.endswith(".Else") and not child_tag.endswith(".Result"):
                continue

            # 1. Selector target
            if child_tag == "Target" or "Target" in child_tag:
                sel_str = child.attrib.get("Selector")
                if not sel_str:
                    for sub in child.iter():
                        if "Selector" in sub.attrib:
                            sel_str = sub.attrib["Selector"]
                            break
                if sel_str:
                    sel_model = build_parsed_selector(
                        raw_selector=sel_str,
                        index=self.selector_counter,
                        hint=disp_name
                    )
                    self.selector_counter += 1
                    self.selectors.append(sel_model)
                    node_selectors.append(sel_model)
                    props["Selector"] = sel_str
                    
            # 2. Result elements (e.g. InputDialog.Result)
            elif child_tag.endswith(".Result"):
                res_val = "".join(child.itertext()).strip()
                if not res_val:
                    for sub in child.iter():
                        sub_t = clean_tag(sub.tag)
                        if sub_t in ["OutArgument", "InOutArgument", "InArgument"] and sub.text:
                            res_val = sub.text.strip()
                            break
                if res_val:
                    props["Result"] = res_val

            # 3. Assign properties
            elif child_tag.endswith(".To"):
                to_val = "".join(child.itertext()).strip()
                if to_val:
                    props["To"] = to_val
            elif child_tag.endswith(".Value"):
                val_val = "".join(child.itertext()).strip()
                if val_val:
                    props["Value"] = val_val

            # 4. If conditions (Then / Else)
            elif child_tag.endswith(".Then"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        sub_act.properties["_branch"] = "Then"
                        child_activities.append(sub_act)
            elif child_tag.endswith(".Else"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        sub_act.properties["_branch"] = "Else"
                        child_activities.append(sub_act)

            # 5. TryCatch blocks
            elif child_tag.endswith(".Try"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        sub_act.properties["_branch"] = "Try"
                        child_activities.append(sub_act)
            elif child_tag.endswith(".Catches"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        sub_act.properties["_branch"] = "Catch"
                        child_activities.append(sub_act)
            elif child_tag.endswith(".Finally"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        sub_act.properties["_branch"] = "Finally"
                        child_activities.append(sub_act)

            # 6. Switch Default & Cases
            elif child_tag.endswith(".Default"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        sub_act.properties["_branch"] = "Default"
                        child_activities.append(sub_act)

            # 7. Bodies: OpenBrowser.Body, ExcelApplicationCard.Body, ForEach.Body, etc.
            elif child_tag.endswith(".Body"):
                for action in child:
                    action_tag = clean_tag(action.tag)
                    if action_tag == "ActivityAction":
                        for sub in action:
                            sub_tag = clean_tag(sub.tag)
                            if not is_metadata_or_prop_tag(sub_tag):
                                sub_act = self._parse_activity_node(sub, level=level + 1)
                                child_activities.append(sub_act)
                    elif not is_metadata_or_prop_tag(action_tag):
                        sub_act = self._parse_activity_node(action, level=level + 1)
                        child_activities.append(sub_act)

            elif child_tag == "ActivityAction":
                for sub in child:
                    sub_tag = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_tag):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        child_activities.append(sub_act)

            # 8. Flowchart steps
            elif child_tag == "StartNode" or child_tag.endswith(".StartNode"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        child_activities.append(sub_act)
            elif child_tag == "FlowStep":
                sub_act = self._parse_activity_node(child, level=level + 1)
                child_activities.append(sub_act)
            elif child_tag == "FlowDecision":
                sub_act = self._parse_activity_node(child, level=level + 1)
                child_activities.append(sub_act)
            elif child_tag.endswith(".Action"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        child_activities.append(sub_act)
            elif child_tag.endswith(".Next"):
                for sub in child:
                    sub_t = clean_tag(sub.tag)
                    if not is_metadata_or_prop_tag(sub_t):
                        sub_act = self._parse_activity_node(sub, level=level + 1)
                        child_activities.append(sub_act)

            # 8b. Form Arguments or Activity Arguments
            elif child_tag.endswith(".Arguments") or child_tag == "Arguments":
                form_args = []
                for sub in child.iter():
                    sub_t = clean_tag(sub.tag)
                    if sub_t in ["InArgument", "OutArgument", "InOutArgument"]:
                        k = None
                        for attr_name, attr_val in sub.attrib.items():
                            if attr_name.endswith("Key") or attr_name == "Key":
                                k = attr_val
                                break
                        var_val = "".join(sub.itertext()).strip()
                        clean_v = clean_uipath_expression(var_val)
                        if k or clean_v:
                            form_args.append({
                                "key": k or clean_v,
                                "variable": clean_v or k,
                                "direction": sub_t
                            })
                if form_args:
                    props["_form_arguments"] = form_args

            # 9. Generic child activity
            elif not is_metadata_or_prop_tag(child_tag) and not child_tag.startswith("Sequence.Variables") and not child_tag.startswith("Flowchart.Variables"):
                # If it has a dot and wasn't a handled container, it's a property node (e.g. HttpClient.Headers)
                if "." in child_tag:
                    # Save property text if present
                    prop_name = child_tag.split(".")[-1]
                    p_txt = "".join(child.itertext()).strip()
                    if p_txt:
                        props[prop_name] = p_txt
                    continue

                case_key = None
                for k, v in child.attrib.items():
                    if k.endswith("Key") or k == "Key":
                        case_key = v
                        break
                        
                sub_act = self._parse_activity_node(child, level=level + 1)
                if case_key is not None:
                    sub_act.properties["_case_key"] = case_key
                    sub_act.properties["_branch"] = "Case"
                child_activities.append(sub_act)

        # Check if attribute has Selector
        if "Selector" in props and not node_selectors:
            sel_model = build_parsed_selector(
                raw_selector=props["Selector"],
                index=self.selector_counter,
                hint=disp_name
            )
            self.selector_counter += 1
            self.selectors.append(sel_model)
            node_selectors.append(sel_model)

        activity = ParsedActivity(
            id=act_id,
            type_name=tag,
            display_name=disp_name,
            properties=props,
            children=child_activities,
            selectors=node_selectors,
            level=level
        )
        self.all_activities.append(activity)
        return activity
