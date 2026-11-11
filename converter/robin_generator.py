import re
from typing import List, Dict, Optional, Set, Tuple
from parser import (
    apply_robin_node_metadata,
    infer_assign_metadata,
    sanitize_robin_script,
)
from .models import WorkflowFile, ParsedActivity, ParsedVariable, ParsedArgument, ParsedSelector, ProjectMetadata
from .activity_converter import (
    indent_lines,
    format_http_error_actions,
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
    convert_uipath_condition_with_casts,
    convert_uipath_expression_to_robin,
    clean_uipath_expression
)

class RobinGenerator:
    def __init__(
        self,
        include_comments: bool = False,
        include_selectors_header: bool = False,
        include_node_metadata: bool = False
    ):
        self.include_comments = include_comments
        self.include_selectors_header = include_selectors_header
        self.include_node_metadata = include_node_metadata
        self.current_workflow_name = "Workflow"
        self.node_counter = 1
        self.input_dialog_vars: Set[str] = set()
        self.text_vars: Set[str] = set()
        self.active_dialog_var: Optional[str] = None

    @staticmethod
    def _join_clean_blocks(blocks: List[str]) -> str:
        """Join converted script blocks removing empty/whitespace-only lines."""
        lines: List[str] = []
        for block in blocks:
            if not block:
                continue
            for line in block.splitlines():
                if line.strip():
                    lines.append(line.rstrip())
        return "\n".join(lines)

    def _wrap_with_numeric_casts(
        self,
        block_lines: List[str],
        cast_vars: List[str],
        saved_dialog_var: Optional[str],
    ) -> List[str]:
        """Prepend Text.ToNumber conversions and guard active InputDialog variables with OK check."""
        if not cast_vars:
            return block_lines

        conv_lines = [f"Text.ToNumber Text: {v} Number=> {v}_Num" for v in cast_vars]
        combined = conv_lines + block_lines
        if saved_dialog_var and saved_dialog_var in cast_vars:
            inner = indent_lines("\n".join(combined), 1)
            return [
                "IF ButtonPressed = $'''OK''' THEN",
                inner,
                "END",
            ]
        return combined

    def generate_for_workflow(
        self,
        wf: WorkflowFile,
        as_subflow: bool = False,
        workflow_label: Optional[str] = None,
    ) -> str:
        """Generate Robin script for a single workflow file."""
        self.current_workflow_name = (
            re.sub(r'[^a-zA-Z0-9_]', '_', workflow_label or wf.display_name) or "Workflow"
        )
        self.node_counter = 1
        self.input_dialog_vars = set()
        self.text_vars = {
            v.name
            for v in wf.variables
            if any(tok in v.type_name.lower() for tok in ("string", "text"))
        }
        var_types: Dict[str, str] = {v.name: v.type_name for v in wf.variables}
        self.active_dialog_var = None

        action_lines: List[str] = []

        # Variable initializations (strictly executable SET statements, deduplicated by name)
        if wf.variables:
            seen_vars: Set[str] = set()
            for var in wf.variables:
                if var.name in seen_vars:
                    continue
                seen_vars.add(var.name)
                pkg, _, _ = infer_assign_metadata(var.name, var.default_value or "", var.type_name)
                if var.default_value and var.default_value != "{x:Null}":
                    val = convert_uipath_expression_to_robin(var.default_value)
                    action_lines.append(f"SET {var.name} TO {val}")
                elif pkg == "Boolean":
                    action_lines.append(f"SET {var.name} TO False")
                elif pkg == "Number":
                    action_lines.append(f"SET {var.name} TO 0")
                else:
                    action_lines.append(f"SET {var.name} TO $''''''")

        # Convert root activity and its tree
        if wf.root_activity:
            converted_tree = self._convert_activity(wf.root_activity)
            if converted_tree:
                action_lines.append(converted_tree)

        body = self._join_clean_blocks(action_lines)
        if self.include_node_metadata:
            body = apply_robin_node_metadata(
                body,
                workflow_name=self.current_workflow_name,
                var_types=var_types,
            )
        body = sanitize_robin_script(
            body,
            keep_node_metadata=self.include_node_metadata,
            preserve_blank_lines=self.include_node_metadata,
        )

        if as_subflow:
            subflow_name = re.sub(r'[^a-zA-Z0-9_]', '_', wf.display_name)
            subflow_code = f"FUNCTION {subflow_name}\n"
            if body:
                subflow_code += indent_lines(body, level=1) + "\n"
            subflow_code += "END FUNCTION"
            wf.subflow_robin = subflow_code
            return subflow_code
        else:
            wf.robin_script = body
            return body

    def generate_full_project(self, project: ProjectMetadata) -> str:
        """Generate a clean Power Automate Desktop Robin script ready for Ctrl+V canvas paste."""
        output_parts: List[str] = []

        # Main Workflow
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
            main_label = project.name if project.name and main_wf.display_name.lower() == "main" else main_wf.display_name
            output_parts.append(self.generate_for_workflow(main_wf, as_subflow=as_sub, workflow_label=main_label))

        # Other subflows
        for wf in other_wfs:
            output_parts.append(self.generate_for_workflow(wf, as_subflow=True))

        if self.include_node_metadata:
            return "\n\n".join([p for p in output_parts if p and p.strip()])
        return self._join_clean_blocks(output_parts)

    def generate_clean_pasteable_script(self, project: ProjectMetadata) -> str:
        """
        Generate a 100% clean, pure PAD Robin script containing ONLY executable actions
        (plus # node_id metadata if enabled and genuine source comments), compatible with PAD Ctrl+V.
        """
        clean_gen = RobinGenerator(
            include_comments=False,
            include_selectors_header=False,
            include_node_metadata=self.include_node_metadata,
        )
        return sanitize_robin_script(
            clean_gen.generate_full_project(project),
            keep_node_metadata=self.include_node_metadata,
            preserve_blank_lines=self.include_node_metadata,
        )

    def _convert_children(self, children: List[ParsedActivity]) -> str:
        """Convert child activities cleanly without double-evaluating nodes."""
        blocks: List[str] = []
        for c in children:
            code = self._convert_activity(c)
            if code and code.strip():
                blocks.append(code)
        return self._join_clean_blocks(blocks)

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
                            f"{indent_lines(format_http_error_actions(status_var, result_var), 1)}\n"
                            f"END"
                        )
                        inner_lines.append(wrapped_block)
                        child.is_mapped = True
                        msg_child.is_mapped = True
                        self.text_vars.discard(status_var)
                        self.active_dialog_var = None
                        i += 2
                        continue

                c_code = self._convert_activity(child)
                if c_code and c_code.strip():
                    inner_lines.append(c_code)
                i += 1

            activity.is_mapped = True
            return self._join_clean_blocks(inner_lines)

        # 2. Control Flow: If
        if tag == "If":
            cond = str(activity.properties.get("Condition", "True"))
            robin_cond, cast_vars = convert_uipath_condition_with_casts(
                cond,
                text_vars=self.text_vars | self.input_dialog_vars,
            )

            then_children = [c for c in activity.children if c.properties.get("_branch") == "Then"]
            else_children = [c for c in activity.children if c.properties.get("_branch") == "Else"]

            saved_dialog_var = self.active_dialog_var
            then_code = self._convert_children(then_children)
            self.active_dialog_var = saved_dialog_var
            else_code = self._convert_children(else_children)
            self.active_dialog_var = None

            res = [f"IF {robin_cond} THEN"]
            if then_code:
                res.append(indent_lines(then_code, 1))
            else:
                res.append("    # Empty Then block")

            if else_code:
                res.append("ELSE")
                res.append(indent_lines(else_code, 1))

            res.append("END")
            res = self._wrap_with_numeric_casts(res, cast_vars, saved_dialog_var)
            activity.is_mapped = True
            activity.robin_code = self._join_clean_blocks(res)
            return activity.robin_code

        # 3. Control Flow: Switch
        if tag == "Switch":
            expr = str(activity.properties.get("Expression", "department"))
            robin_expr = clean_uipath_expression(expr)
            lines = [f"SWITCH {robin_expr}"]

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

            lines.append("END")
            activity.is_mapped = True
            activity.robin_code = self._join_clean_blocks(lines)
            return activity.robin_code

        # 4. Loops: ForEach, ForEachRow, While, DoWhile
        if tag in ["ForEach", "ForEachRow"]:
            coll = str(activity.properties.get("Values") or activity.properties.get("DataTable") or "Items")
            coll_clean = clean_uipath_expression(coll)
            item_name = "CurrentItem" if tag == "ForEach" else "CurrentRow"

            inner_code = self._convert_children(activity.children)
            res = [f"LOOP FOREACH {item_name} IN {coll_clean}"]
            if inner_code:
                res.append(indent_lines(inner_code, 1))
            else:
                res.append("    # Loop body")
            res.append("END")
            activity.is_mapped = True
            activity.robin_code = self._join_clean_blocks(res)
            return activity.robin_code

        if tag in ["While", "DoWhile"]:
            cond = str(activity.properties.get("Condition", "True"))
            robin_cond, cast_vars = convert_uipath_condition_with_casts(
                cond,
                text_vars=self.text_vars | self.input_dialog_vars,
            )
            saved_dialog_var = self.active_dialog_var
            inner_code = self._convert_children(activity.children)
            self.active_dialog_var = None

            res = [f"LOOP WHILE {robin_cond}"]
            if inner_code:
                res.append(indent_lines(inner_code, 1))
            res.append("END")
            res = self._wrap_with_numeric_casts(res, cast_vars, saved_dialog_var)
            activity.is_mapped = True
            activity.robin_code = self._join_clean_blocks(res)
            return activity.robin_code

        # 5. TryCatch
        if tag == "TryCatch":
            try_children = [c for c in activity.children if c.properties.get("_branch") == "Try"]
            catch_children = [c for c in activity.children if c.properties.get("_branch") == "Catch"]
            finally_children = [c for c in activity.children if c.properties.get("_branch") == "Finally"]

            try_code = self._convert_children(try_children)
            catch_code = self._convert_children(catch_children)
            finally_code = self._convert_children(finally_children)

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
            activity.robin_code = self._join_clean_blocks(res)
            return activity.robin_code

        # 6. OpenBrowser / UseApplicationOrBrowser
        if tag in ["OpenBrowser", "UseApplicationOrBrowser"]:
            inner_code = self._convert_children(activity.children)
            code = convert_open_browser(activity, inner_code)
            activity.is_mapped = True
            activity.robin_code = self._join_clean_blocks([code])
            return activity.robin_code

        # 7. ExcelApplicationScope / ExcelApplicationCard
        if tag in ["ExcelApplicationScope", "ExcelApplicationCard"]:
            inner_code = self._convert_children(activity.children)
            code = convert_excel_scope(activity, inner_code)
            activity.is_mapped = True
            activity.robin_code = self._join_clean_blocks([code])
            return activity.robin_code

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

            # Track InputDialog / text variable state for Text.ToNumber + Cancel guard
            if tag == "InputDialog":
                res_var = re.sub(r'[\[\]]', '', str(activity.properties.get("Result", "UserInput"))).strip() or "UserInput"
                self.input_dialog_vars.add(res_var)
                self.text_vars.add(res_var)
                self.active_dialog_var = res_var
            elif tag == "MessageBox":
                self.active_dialog_var = None
            elif tag in ("Assign", "MultipleAssign"):
                to_var = clean_uipath_expression(str(activity.properties.get("To", ""))).strip()
                to_var = re.sub(r'[\[\]]', '', to_var).strip()
                if to_var:
                    if code.startswith(f"SET {to_var} TO $'''"):
                        self.text_vars.add(to_var)
                        self.input_dialog_vars.discard(to_var)
                    elif code.startswith(f"SET {to_var} TO "):
                        rhs = code[len(f"SET {to_var} TO "):].strip()
                        if re.match(r'^-?\d+(?:\.\d+)?$', rhs) or ".Count%" in rhs or ".Length%" in rhs:
                            self.text_vars.discard(to_var)
                            self.input_dialog_vars.discard(to_var)

            activity.robin_code = self._join_clean_blocks([code]) if code else ""
            return activity.robin_code

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
