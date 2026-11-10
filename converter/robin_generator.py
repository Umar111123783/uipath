import re
import hashlib
from typing import List, Dict, Optional
from .models import WorkflowFile, ParsedActivity, ParsedVariable, ParsedArgument, ParsedSelector, ProjectMetadata
from .activity_converter import (
    indent_lines,
    convert_assign,
    convert_delay,
    convert_message_box,
    convert_input_dialog,
    convert_log_message,
    convert_write_line,
    convert_http_client,
    convert_deserialize_json,
    convert_build_data_table,
    convert_add_data_row,
    convert_open_browser,
    convert_close_tab,
    convert_navigate_to,
    convert_click,
    convert_type_into,
    convert_get_value,
    convert_send_hotkey,
    convert_excel_scope,
    convert_read_range,
    convert_write_range,
    convert_excel_save,
    convert_excel_close,
    convert_read_text_file,
    convert_write_text_file,
    convert_append_text,
    convert_copy_file,
    convert_move_file,
    convert_delete_file,
    convert_create_directory,
    convert_start_process,
    convert_kill_process,
    convert_invoke_workflow,
    convert_show_form,
    convert_break,
    convert_continue,
    convert_comment
)
from .expression_parser import (
    convert_uipath_condition_to_robin,
    convert_uipath_expression_to_robin,
    clean_uipath_expression
)

PACKAGE_MAP = {
    "Assign": ("String", "assign", "assign"),
    "MultipleAssign": ("String", "assign", "assign"),
    "Delay": ("Delay", "delay", "delay"),
    "MessageBox": ("MessageBox", "messageBox", "show message"),
    "InputDialog": ("Display", "inputDialog", "input dialog"),
    "ShowFormActivity": ("Display", "inputDialog", "input dialog"),
    "HttpClient": ("Web", "invokeWebService", "invoke web service"),
    "NetHttpRequest": ("Web", "invokeWebService", "invoke web service"),
    "DeserializeJson": ("Json", "deserializeJson", "convert json to custom object"),
    "DeserializeJsonArray": ("Json", "deserializeJson", "convert json to custom object"),
    "BuildDataTable": ("DataTable", "buildDataTable", "create new datatable"),
    "AddDataRow": ("DataTable", "addDataRow", "add row to datatable"),
    "If": ("If", "if", "if"),
    "ForEach": ("Loop", "loop", "loop foreach"),
    "ExcelApplicationScope": ("Excel", "excelScope", "launch excel"),
    "ExcelWriteRange": ("Excel", "writeCell", "write datatable to excel"),
    "WriteRangeX": ("Excel", "writeCell", "write datatable to excel"),
    "ExcelReadRange": ("Excel", "readRange", "read excel range"),
    "ReadRangeX": ("Excel", "readRange", "read excel range"),
    "ExcelSaveWorkbook": ("Excel", "saveExcel", "save excel"),
    "ExcelCloseWorkbook": ("Excel", "closeExcel", "close excel"),
    "OpenBrowser": ("WebAutomation", "openBrowser", "launch chrome"),
    "Click": ("WebAutomation", "click", "click"),
    "TypeInto": ("WebAutomation", "typeInto", "populate text field"),
    "GetValue": ("WebAutomation", "getValue", "get text"),
    "Comment": ("Comment", "Comment", "comment"),
    "CommentOut": ("Comment", "Comment", "comment")
}

class RobinGenerator:
    def __init__(
        self,
        include_comments: bool = True,
        include_selectors_header: bool = True,
        include_node_metadata: bool = False
    ):
        self.include_comments = include_comments
        self.include_selectors_header = include_selectors_header
        self.include_node_metadata = include_node_metadata
        self.current_workflow_name = "Workflow"
        self.node_counter = 1

    def _create_node_comment(self, package: str, action: str, resolved: str) -> str:
        """Create a structured Automation Anywhere / Robin node metadata comment."""
        seed = f"{self.current_workflow_name}_{self.node_counter:05d}_{package}_{action}"
        hex8 = hashlib.md5(seed.encode("utf-8")).hexdigest()[:8]
        node_str = f"1.{self.node_counter:05d}.{hex8}"
        self.node_counter += 1
        return f"# node_id={self.current_workflow_name} {node_str}; package={package}; action={action}; resolved={resolved}"

    def generate_for_workflow(self, wf: WorkflowFile, as_subflow: bool = False) -> str:
        """Generate Robin script for a single workflow file."""
        self.current_workflow_name = re.sub(r'[^a-zA-Z0-9_]', '_', wf.display_name) or "Workflow"
        self.node_counter = 1
        lines: List[str] = []
        
        # Header comments
        if self.include_comments:
            lines.append(f"# ========================================================")
            lines.append(f"# Converted from UiPath Workflow: {wf.filename}")
            if wf.arguments:
                lines.append(f"# Arguments ({len(wf.arguments)}):")
                for arg in wf.arguments:
                    lines.append(f"#   - [{arg.direction}] %{arg.name}% ({arg.type_name})")
            if wf.variables:
                lines.append(f"# Variables ({len(wf.variables)}):")
                for var in wf.variables:
                    lines.append(f"#   - %{var.name}% ({var.type_name})")
            lines.append(f"# ========================================================")
            lines.append("")

        action_lines: List[str] = []

        if self.include_node_metadata:
            banner_comment = self._create_node_comment("Comment", "Comment", "comment")
            action_lines.append(banner_comment)
            action_lines.append(f"# ********************************************************TASK NAME: {self.current_workflow_name} ****************************************************************************************************************************************************")
            action_lines.append("")

        # Variable initializations
        if wf.variables:
            action_lines.append("# --- Initialize Variables ---")
            action_lines.append("")
            for var in wf.variables:
                vtype = var.type_name.lower()
                if "int" in vtype or "num" in vtype or "double" in vtype:
                    var_pkg = "Number"
                    act = "assignToNumber"
                elif "bool" in vtype:
                    var_pkg = "Boolean"
                    act = "assign"
                elif "list" in vtype or "array" in vtype:
                    var_pkg = "List"
                    act = "assign"
                elif "datatable" in vtype:
                    var_pkg = "DataTable"
                    act = "assign"
                elif "jobject" in vtype or "customobject" in vtype:
                    var_pkg = "CustomObject"
                    act = "assign"
                else:
                    var_pkg = "String"
                    act = "assign"

                if self.include_node_metadata:
                    action_lines.append(self._create_node_comment(var_pkg, act, "assign"))

                if var.default_value and var.default_value != "{x:Null}":
                    val = convert_uipath_expression_to_robin(var.default_value)
                    action_lines.append(f"SET {var.name} TO {val}")
                elif var_pkg == "Boolean":
                    action_lines.append(f"SET {var.name} TO $'''constant'''")
                elif var_pkg == "Number":
                    action_lines.append(f"SET {var.name} TO $'''0'''")
                else:
                    action_lines.append(f"SET {var.name} TO $''''''")
                action_lines.append("")

        # Convert root activity and its tree
        if wf.root_activity:
            converted_tree = self._convert_activity(wf.root_activity)
            if converted_tree:
                action_lines.append(converted_tree)
        else:
            action_lines.append("# No executable activities found in workflow.")

        body = "\n".join(action_lines)

        if as_subflow:
            subflow_name = re.sub(r'[^a-zA-Z0-9_]', '_', wf.display_name)
            subflow_code = f"FUNCTION {subflow_name}\n"
            subflow_code += indent_lines(body, level=1) + "\n"
            subflow_code += "END FUNCTION"
            wf.subflow_robin = subflow_code
            return subflow_code
        else:
            wf.robin_script = body
            return body

    def generate_full_project(self, project: ProjectMetadata) -> str:
        """Generate a complete Power Automate Desktop flow script with all subflows."""
        output_parts: List[str] = []

        # 1. Header & Project Info
        if self.include_comments:
            output_parts.append("# ========================================================")
            output_parts.append(f"# POWER AUTOMATE DESKTOP (ROBIN SCRIPT)")
            output_parts.append(f"# Project: {project.name}")
            output_parts.append(f"# Total Workflows: {len(project.workflows)}")
            output_parts.append(f"# Total Activities: {project.total_activities}")
            output_parts.append(f"# Conversion Success Rate: {(project.total_mapped / max(1, project.total_activities) * 100):.1f}%")
            output_parts.append("# Instructions: Copy all text below and paste (Ctrl+V) into")
            output_parts.append("# Power Automate Desktop flow designer canvas.")
            output_parts.append("# ========================================================")
            output_parts.append("")

        # 2. Control Repository / Selectors
        if self.include_selectors_header and project.all_selectors:
            output_parts.append("# [ControlRepositoryFolder]")
            output_parts.append("# --- UI Elements Mapped from UiPath Selectors ---")
            for sel in project.all_selectors:
                output_parts.append(f"# Control: {sel.control_code}")
                if sel.xpath:
                    output_parts.append(f"#   XPath: {sel.xpath}")
                if sel.css:
                    output_parts.append(f"#   CSS: {sel.css}")
                clean_raw = sel.uipath_raw.replace("\n", " ").strip()
                output_parts.append(f"#   UiPath: {clean_raw}")
            output_parts.append("")

        # 3. Main Workflow
        main_wf = None
        other_wfs = []
        for wf in project.workflows:
            if wf.is_main or wf.filename.lower() == project.main_file.lower():
                main_wf = wf
            else:
                other_wfs.append(wf)

        if not main_wf and project.workflows:
            main_wf = project.workflows[0]
            other_wfs = project.workflows[1:]

        if main_wf:
            # Emit bare actions for single-flow bots for direct Ctrl+V canvas paste in PAD
            as_sub = len(other_wfs) > 0
            output_parts.append(self.generate_for_workflow(main_wf, as_subflow=as_sub))
            output_parts.append("")

        # 4. Other subflows
        for wf in other_wfs:
            output_parts.append(self.generate_for_workflow(wf, as_subflow=True))
            output_parts.append("")

        return "\n".join([p for p in output_parts if p.strip()]).strip()

    def generate_clean_pasteable_script(self, project: ProjectMetadata) -> str:
        """
        Generate a 100% clean, pure PAD Robin script containing ONLY executable actions,
        strictly compatible with Power Automate Desktop clipboard Ctrl+V parsing.
        """
        clean_gen = RobinGenerator(include_comments=False, include_selectors_header=False)
        return clean_gen.generate_full_project(project)

    def _convert_activity(self, activity: ParsedActivity) -> str:
        """Convert a ParsedActivity and its children into Robin script."""
        tag = activity.type_name
        
        # 1. Containers: Sequence, Flowchart, FlowStep, StateMachine, ExcelProcessScopeX
        if tag in ["Sequence", "Flowchart", "FlowStep", "StateMachine", "ExcelProcessScopeX"]:
            inner_lines = []
            i = 0
            while i < len(activity.children):
                child = activity.children[i]
                
                # Check if child is HttpClient / NetHttpRequest followed immediately by a response MessageBox
                if child.type_name in ["HttpClient", "NetHttpRequest"]:
                    if i + 1 < len(activity.children) and activity.children[i+1].type_name == "MessageBox":
                        msg_child = activity.children[i+1]
                        http_code = convert_http_client(child, include_status_check=False)
                        msg_code = convert_message_box(msg_child)
                        status_var = re.sub(r'[\[\]]', '', str(child.properties.get("StatusCode", "responseStatus"))).strip() or "responseStatus"
                        result_var = re.sub(r'[\[\]]', '', str(child.properties.get("Result", "responseString"))).strip() or "responseString"
                        
                        wrapped_block = (
                            f"{http_code}\n"
                            f"IF {status_var} >= 200 AND {status_var} < 300 THEN\n"
                            f"{indent_lines(msg_code, 1)}\n"
                            f"ELSE\n"
                            f"    Display.ShowMessageDialog.ShowMessage Title: $'''API Error''' "
                            f"Message: $'''HTTP request failed with status: %{status_var}%\\r\\n%{result_var}%''' "
                            f"Icon: Display.Icon.Error Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed\n"
                            f"    FlowControl.StopFlow Execution: FlowControl.StopFlowMode.StopNormally\n"
                            f"END"
                        )
                        inner_lines.append(wrapped_block)
                        child.is_mapped = True
                        msg_child.is_mapped = True
                        i += 2
                        continue
                        
                c_code = self._convert_activity(child)
                if c_code:
                    inner_lines.append(c_code)
                i += 1
                
            activity.is_mapped = True
            return "\n".join(inner_lines)

        # 2. Control Flow: If
        if tag == "If":
            cond = str(activity.properties.get("Condition", "True"))
            robin_cond = convert_uipath_condition_to_robin(cond)
            
            then_children = [c for c in activity.children if c.properties.get("_branch") == "Then"]
            else_children = [c for c in activity.children if c.properties.get("_branch") == "Else"]
            
            then_code = "\n".join([self._convert_activity(c) for c in then_children if self._convert_activity(c)])
            else_code = "\n".join([self._convert_activity(c) for c in else_children if self._convert_activity(c)])
            
            res = []
            if self.include_node_metadata:
                res.append(self._create_node_comment("If", "if", "if"))
            res.append(f"IF {robin_cond} THEN")
            if then_code:
                res.append(indent_lines(then_code, 1))
            else:
                res.append("    # Empty Then block")
                
            if else_code:
                if self.include_node_metadata:
                    res.append(f"\n{self._create_node_comment('If', 'else', 'else')}")
                res.append("ELSE")
                res.append(indent_lines(else_code, 1))
                
            res.append("END")
            activity.is_mapped = True
            activity.robin_code = "\n".join(res)
            return activity.robin_code

        # 3. Control Flow: Switch
        if tag == "Switch":
            expr = str(activity.properties.get("Expression", "department"))
            robin_expr = clean_uipath_expression(expr)
            lines = [f"SWITCH %{robin_expr}%"]
            
            for child in activity.children:
                branch = child.properties.get("_branch")
                case_key = child.properties.get("_case_key")
                inner_code = self._convert_activity(child)
                
                if branch == "Case" or case_key:
                    val_code = convert_uipath_expression_to_robin(str(case_key))
                    lines.append(f"    CASE {val_code}")
                    if inner_code:
                        lines.append(indent_lines(inner_code, 2))
                elif branch == "Default":
                    lines.append("    DEFAULT")
                    if inner_code:
                        lines.append(indent_lines(inner_code, 2))
                else:
                    if inner_code:
                        lines.append(indent_lines(inner_code, 1))
                        
            lines.append("END SWITCH")
            activity.is_mapped = True
            activity.robin_code = "\n".join(lines)
            return activity.robin_code

        # 4. Loops: ForEach, ForEachRow, While, DoWhile
        if tag in ["ForEach", "ForEachRow"]:
            coll = str(activity.properties.get("Values") or activity.properties.get("DataTable") or "Items")
            coll_clean = clean_uipath_expression(coll)
            item_name = "CurrentItem" if tag == "ForEach" else "CurrentRow"
            
            inner_code = "\n".join([self._convert_activity(c) for c in activity.children if self._convert_activity(c)])
            res = [f"LOOP FOREACH {item_name} IN {coll_clean}"]
            if inner_code:
                res.append(indent_lines(inner_code, 1))
            else:
                res.append("    # Loop body")
            res.append("END")
            activity.is_mapped = True
            if self.include_node_metadata:
                res.insert(0, self._create_node_comment("Loop", "loop", "loop foreach"))
            activity.robin_code = "\n".join(res)
            return activity.robin_code

        if tag in ["While", "DoWhile"]:
            cond = str(activity.properties.get("Condition", "True"))
            robin_cond = convert_uipath_condition_to_robin(cond)
            inner_code = "\n".join([self._convert_activity(c) for c in activity.children if self._convert_activity(c)])
            res = [f"LOOP WHILE {robin_cond}"]
            if inner_code:
                res.append(indent_lines(inner_code, 1))
            res.append("END")
            activity.is_mapped = True
            if self.include_node_metadata:
                res.insert(0, self._create_node_comment("Loop", "loop", "loop while"))
            activity.robin_code = "\n".join(res)
            return activity.robin_code

        # 5. TryCatch
        if tag == "TryCatch":
            try_children = [c for c in activity.children if c.properties.get("_branch") == "Try"]
            catch_children = [c for c in activity.children if c.properties.get("_branch") == "Catch"]
            finally_children = [c for c in activity.children if c.properties.get("_branch") == "Finally"]
            
            try_code = "\n".join([self._convert_activity(c) for c in try_children if self._convert_activity(c)])
            catch_code = "\n".join([self._convert_activity(c) for c in catch_children if self._convert_activity(c)])
            finally_code = "\n".join([self._convert_activity(c) for c in finally_children if self._convert_activity(c)])
            
            res = ["# [Try Block Start]"]
            if try_code:
                res.append(try_code)
            if catch_code:
                res.append("# [Exception Catch Block]")
                res.append(catch_code)
            if finally_code:
                res.append("# [Finally Block]")
                res.append(finally_code)
            res.append("# [Try Block End]")
            activity.is_mapped = True
            activity.robin_code = "\n".join(res)
            return activity.robin_code

        # 6. OpenBrowser / UseApplicationOrBrowser
        if tag in ["OpenBrowser", "UseApplicationOrBrowser"]:
            inner_code = "\n".join([self._convert_activity(c) for c in activity.children if self._convert_activity(c)])
            code = convert_open_browser(activity, inner_code)
            activity.is_mapped = True
            activity.robin_code = code
            return code

        # 7. ExcelApplicationScope / ExcelApplicationCard
        if tag in ["ExcelApplicationScope", "ExcelApplicationCard"]:
            inner_code = "\n".join([self._convert_activity(c) for c in activity.children if self._convert_activity(c)])
            code = convert_excel_scope(activity, inner_code)
            activity.is_mapped = True
            activity.robin_code = code
            return code

        # 8. Discrete Activity Mappings
        mapping_funcs = {
            "Assign": convert_assign,
            "MultipleAssign": convert_assign,
            "Delay": convert_delay,
            "MessageBox": convert_message_box,
            "InputDialog": convert_input_dialog,
            "LogMessage": convert_log_message,
            "WriteLine": convert_write_line,
            "HttpClient": convert_http_client,
            "NetHttpRequest": convert_http_client,
            "DeserializeJson": convert_deserialize_json,
            "DeserializeJsonArray": convert_deserialize_json,
            "BuildDataTable": convert_build_data_table,
            "AddDataRow": convert_add_data_row,
            "CloseTab": convert_close_tab,
            "CloseWindow": convert_close_tab,
            "CloseApplication": convert_close_tab,
            "NavigateTo": convert_navigate_to,
            "Click": convert_click,
            "TypeInto": convert_type_into,
            "GetValue": convert_get_value,
            "GetFullText": convert_get_value,
            "GetAttribute": convert_get_value,
            "SendHotkey": convert_send_hotkey,
            "ExcelReadRange": convert_read_range,
            "ReadRangeX": convert_read_range,
            "ExcelWriteRange": convert_write_range,
            "WriteRangeX": convert_write_range,
            "ExcelReadCell": convert_read_range,
            "ExcelWriteCell": convert_write_range,
            "ExcelSaveWorkbook": convert_excel_save,
            "ExcelCloseWorkbook": convert_excel_close,
            "ReadTextFile": convert_read_text_file,
            "WriteTextFile": convert_write_text_file,
            "AppendText": convert_append_text,
            "CopyFile": convert_copy_file,
            "MoveFile": convert_move_file,
            "Delete": convert_delete_file,
            "CreateDirectory": convert_create_directory,
            "StartProcess": convert_start_process,
            "OpenApplication": convert_start_process,
            "KillProcess": convert_kill_process,
            "InvokeWorkflowFile": convert_invoke_workflow,
            "ShowFormActivity": convert_show_form,
            "Break": convert_break,
            "Continue": convert_continue,
            "Comment": convert_comment,
            "CommentOut": convert_comment
        }

        if tag in mapping_funcs:
            code = mapping_funcs[tag](activity)
            activity.is_mapped = True
            if self.include_node_metadata and code:
                pkg, action, resolved = PACKAGE_MAP.get(tag, ("Core", tag, tag.lower()))
                meta_comment = self._create_node_comment(pkg, action, resolved)
                code = f"{meta_comment}\n{code}"
            activity.robin_code = code
            return code

        # Unmapped / Custom Activity Fallback
        activity.is_mapped = False
        prop_str = ", ".join([f"{k}='{v}'" for k, v in activity.properties.items() if not k.startswith("_") and not k.startswith("sap")][:4])
        comment_lines = [
            f"# [UiPath Unmapped Activity]: <{tag}> (DisplayName: '{activity.display_name}')",
            f"#   Properties: {prop_str}" if prop_str else "#   Properties: None",
            f"#   TODO: Add Power Automate Desktop equivalent for '{activity.display_name}'"
        ]
        
        if activity.children:
            for child in activity.children:
                c_code = self._convert_activity(child)
                if c_code:
                    comment_lines.append(c_code)
                    
        activity.robin_code = "\n".join(comment_lines)
        return activity.robin_code
