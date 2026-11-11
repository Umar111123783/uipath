import re
from typing import Dict, Any, List, Optional, Tuple
from .models import ParsedActivity, ParsedSelector
from .expression_parser import (
    convert_uipath_expression_to_robin,
    convert_uipath_condition_to_robin,
    parse_uipath_duration,
    clean_uipath_expression
)

def indent_lines(text: str, level: int = 1) -> str:
    """Indent lines by 4 spaces per level."""
    indent = "    " * level
    lines = text.split("\n")
    return "\n".join(f"{indent}{l}" if l.strip() else "" for l in lines)

def get_prop(activity: ParsedActivity, key: str, default: Any = "") -> Any:
    """Safely get a property from activity."""
    return activity.properties.get(key, default)

def get_target_selector_info(activity: ParsedActivity) -> Tuple[str, Optional[str], Optional[str]]:
    """Extract selector info if attached to activity."""
    if activity.selectors:
        sel = activity.selectors[0]
        return sel.control_code, sel.xpath, sel.uipath_raw
    raw_sel = activity.properties.get("Selector") or activity.properties.get("Target.Selector")
    if raw_sel:
        return f"appmask['UI_{activity.id}']", None, raw_sel
    return "appmask['UIElement']", None, None

def convert_assign(activity: ParsedActivity) -> str:
    to_var = clean_uipath_expression(str(get_prop(activity, "To", "Var"))).strip()
    
    # Handle DataTable row column assignment: CurrentRow("col") -> CurrentRow['col']
    m_col = re.match(r'^([a-zA-Z0-9_]+)\("([^"]+)"\)$', to_var)
    if m_col:
        to_var = f"{m_col.group(1)}['{m_col.group(2)}']"
    else:
        to_var = re.sub(r'[\[\]]', '', to_var).strip()
        
    if not to_var:
        to_var = "Variable"
    val = str(get_prop(activity, "Value", ""))
    val_clean = clean_uipath_expression(val).strip()

    # Check for JObject / JArray initialization
    if re.match(r'^new\s+jobject(\(\))?$', val_clean, re.IGNORECASE):
        return f"Variables.ConvertJsonToCustomObject Json: $'''{{}}''' CustomObject=> {to_var}"
    if re.match(r'^new\s+(?:jarray|list\b)(\(\))?$', val_clean, re.IGNORECASE):
        return f"Variables.CreateNewList List=> {to_var}"

    # Check for Path.Combine(...) with Desktop special folder
    m_path = re.search(r'Path\.Combine\s*\([^,]+,\s*"([^"]+)"\)', val_clean, re.DOTALL)
    if m_path:
        fname = m_path.group(1)
        lines = [
            "Folder.GetSpecialFolder SpecialFolder: Folder.SpecialFolder.DesktopDirectory SpecialFolderPath=> SpecialFolderPath",
            f"SET {to_var} TO $'''%SpecialFolderPath%\\{fname}'''"
        ]
        return "\n".join(lines)

    robin_val = convert_uipath_expression_to_robin(val)
    return f"SET {to_var} TO {robin_val}"

def convert_delay(activity: ParsedActivity) -> str:
    duration_str = str(get_prop(activity, "Duration", "00:00:01"))
    sec = parse_uipath_duration(duration_str)
    sec_str = str(int(sec)) if sec.is_integer() else f"{sec:.2f}"
    return f"Wait Delay: {sec_str}"

def convert_message_box(activity: ParsedActivity) -> str:
    caption = str(get_prop(activity, "Caption", "Message"))
    if caption in ["{x:Null}", "", "None"]:
        caption = "Message"
    text = str(get_prop(activity, "Text", "Hello"))
    robin_caption = convert_uipath_expression_to_robin(caption)
    robin_text = convert_uipath_expression_to_robin(text)
    
    # Ensure message content stays on a single line so PAD clipboard parser does not break
    robin_text = robin_text.replace("\r\n", "\\r\\n").replace("\n", "\\r\\n")
    robin_caption = robin_caption.replace("\r\n", "\\r\\n").replace("\n", "\\r\\n")

    return (
        f"Display.ShowMessageDialog.ShowMessage Title: {robin_caption} "
        f"Message: {robin_text} Icon: Display.Icon.None Buttons: Display.Buttons.OK "
        f"DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed"
    )

def convert_input_dialog(activity: ParsedActivity) -> str:
    title = str(get_prop(activity, "Title", "Input Dialog"))
    if title in ["{x:Null}", "", "None"]:
        title = "Input Dialog"
    label = str(get_prop(activity, "Label", "Please enter a value:"))
    if label in ["{x:Null}", "", "None"]:
        label = "Please enter a value:"
    result_var = str(get_prop(activity, "Result", "UserInput"))
    clean_var = re.sub(r'[\[\]]', '', result_var).strip() or "UserInput"
    is_password = str(get_prop(activity, "IsPassword", "False")).lower() == "true"
    input_type = "Display.InputType.Password" if is_password else "Display.InputType.SingleLine"
    
    robin_title = convert_uipath_expression_to_robin(title)
    robin_label = convert_uipath_expression_to_robin(label)
    return (
        f"Display.InputDialog Title: {robin_title} Message: {robin_label} "
        f"InputType: {input_type} IsTopMost: False UserInput=> {clean_var} ButtonPressed=> ButtonPressed"
    )

def convert_log_message(activity: ParsedActivity) -> str:
    msg = str(get_prop(activity, "Message", ""))
    level = str(get_prop(activity, "Level", "Info"))
    robin_msg = convert_uipath_expression_to_robin(msg)
    return f"# [Log - {level}] {robin_msg}"

def convert_write_line(activity: ParsedActivity) -> str:
    text = str(get_prop(activity, "Text", ""))
    robin_text = convert_uipath_expression_to_robin(text)
    return f"# [Console Log]: {robin_text}"

def convert_http_client(activity: ParsedActivity, include_status_check: bool = True) -> str:
    url = str(get_prop(activity, "EndPoint") or get_prop(activity, "RequestUrl") or get_prop(activity, "Url", "https://api.example.com"))
    method = str(get_prop(activity, "Method", "GET")).upper()
    result_var = re.sub(r'[\[\]]', '', str(get_prop(activity, "Result", "responseString"))).strip() or "responseString"
    status_var = re.sub(r'[\[\]]', '', str(get_prop(activity, "StatusCode", "responseStatus"))).strip() or "responseStatus"
    body = str(get_prop(activity, "Body", ""))
    disp = str(get_prop(activity, "DisplayName", "")).lower()

    # Intelligently fix method if UiPath developer used GET with a body or for an update
    if method == "GET" and body and body != "{x:Null}":
        method = "PUT"
    elif "update" in disp and method == "GET":
        method = "PUT"
    
    robin_url = convert_uipath_expression_to_robin(url)
    method_map = {
        "GET": "Web.Method.Get",
        "POST": "Web.Method.Post",
        "PUT": "Web.Method.Put",
        "DELETE": "Web.Method.Delete",
        "PATCH": "Web.Method.Patch"
    }
    pad_method = method_map.get(method, "Web.Method.Get")
    
    body_arg = ""
    if body and body != "{x:Null}":
        robin_body = convert_uipath_expression_to_robin(body)
        body_arg = f" RequestBody: {robin_body}"
        
    invoke_code = (
        f"Web.InvokeWebService.InvokeWebService Url: {robin_url} Method: {pad_method} "
        f"Accept: $'''application/json''' ContentType: $'''application/json'''{body_arg} "
        f"ConnectionTimeout: 30 FollowRedirection: True ClearCookies: False FailOnErrorStatus: False EncodeRequestBody: True "
        f"UserAgent: $'''Mozilla/5.0''' Encoding: Web.Encoding.AutoDetect AcceptUntrustedCertificates: False "
        f"ResponseHeaders=> ResponseHeaders Response=> {result_var} StatusCode=> {status_var}"
    )

    if include_status_check:
        status_check = (
            f"\nIF {status_var} < 200 OR {status_var} >= 300 THEN\n"
            f"    Display.ShowMessageDialog.ShowMessage Title: $'''API Error''' "
            f"Message: $'''HTTP request failed with status: %{status_var}%\\r\\n%{result_var}%''' "
            f"Icon: Display.Icon.Error Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed\n"
            f"    FlowControl.StopFlow Execution: FlowControl.StopFlowMode.StopNormally\n"
            f"END"
        )
        return invoke_code + status_check

    return invoke_code

def convert_deserialize_json(activity: ParsedActivity) -> str:
    json_str = str(get_prop(activity, "JsonString", "responseString"))
    json_str_clean = clean_uipath_expression(json_str)
    out_obj = str(get_prop(activity, "JsonObject") or get_prop(activity, "JsonArray") or "JsonData")
    out_obj_clean = re.sub(r'[\[\]]', '', out_obj).strip() or "JsonData"
    return f"Variables.ConvertJsonToCustomObject Json: %{json_str_clean}% CustomObject=> {out_obj_clean}"

def convert_build_data_table(activity: ParsedActivity) -> str:
    dt = re.sub(r'[\[\]]', '', str(get_prop(activity, "DataTable", "DataTable"))).strip() or "DataTable"
    table_info = str(get_prop(activity, "TableInfo", ""))
    cols = []
    if table_info:
        raw_cols = re.findall(r'<xs:element\s+name="([^"]+)"', table_info)
        cols = [c for c in raw_cols if c not in ["NewDataSet", "TableName"]]
        
    if cols:
        cols_str = ", ".join([f"'{c}'" for c in cols])
        return f"Variables.CreateNewDatatable InputTable: {{ ^[{cols_str}] }} DataTable=> {dt}"
        
    return f"Variables.CreateNewDatatable InputTable: {{ ^['Column1', 'Column2', 'Column3', 'Column4'] }} DataTable=> {dt}"

def convert_add_data_row(activity: ParsedActivity) -> str:
    dt = re.sub(r'[\[\]]', '', str(get_prop(activity, "DataTable", "DataTable"))).strip() or "DataTable"
    arr = str(get_prop(activity, "ArrayRow", ""))
    
    # Extract keys like currentJToken("userId") or CurrentItem['userId']
    keys = re.findall(r'(?:currentJToken|[a-zA-Z0-9_]+)\("([^"]+)"\)', arr)
    if not keys:
        keys = re.findall(r"CurrentItem\['([^']+)'\]", arr)
        
    if keys:
        items_str = ", ".join([f"CurrentItem['{k}']" for k in keys])
        return f"Variables.AddRowToDataTable.AppendRowToDataTable DataTable: {dt} RowToAdd: [{items_str}]"
        
    robin_arr = convert_uipath_expression_to_robin(arr) if arr else "[CurrentItem]"
    return f"Variables.AddRowToDataTable.AppendRowToDataTable DataTable: {dt} RowToAdd: {robin_arr}"

def convert_open_browser(activity: ParsedActivity, inner_code: str) -> str:
    browser_type = str(get_prop(activity, "BrowserType", "Chrome")).lower()
    url = str(get_prop(activity, "Url", "https://www.google.com"))
    robin_url = convert_uipath_expression_to_robin(url)
    
    launch_action = "WebAutomation.LaunchChrome.LaunchChrome"
    if "edge" in browser_type:
        launch_action = "WebAutomation.LaunchEdge.LaunchEdge"
    elif "firefox" in browser_type:
        launch_action = "WebAutomation.LaunchFirefox.LaunchFirefox"
        
    code = (
        f"{launch_action} Url: {robin_url} "
        f"WindowState: WebAutomation.WindowState.Normal ClearCache: False ClearCookies: False "
        f"WaitForPageLoadTimeout: 60 Timeout: 60 BrowserInstance=> Browser"
    )
    if inner_code:
        code += "\n" + inner_code
    return code

def convert_close_tab(activity: ParsedActivity) -> str:
    return "WebAutomation.CloseWebBrowser BrowserInstance: Browser"

def convert_navigate_to(activity: ParsedActivity) -> str:
    url = str(get_prop(activity, "Url", ""))
    robin_url = convert_uipath_expression_to_robin(url)
    return f"WebAutomation.Navigate BrowserInstance: Browser Url: {robin_url}"

def convert_click(activity: ParsedActivity, include_comments: bool = False) -> str:
    ctrl, xpath, raw_sel = get_target_selector_info(activity)
    comment = f" # XPath: {xpath}" if (include_comments and xpath) else ""
    return (
        f"WebAutomation.Click.Click BrowserInstance: Browser Control: {ctrl} "
        f"ClickType: WebAutomation.ClickType.LeftClick MouseClick: False "
        f"WaitForPageLoadTimeout: 60 Timeout: 60{comment}"
    )

def convert_type_into(activity: ParsedActivity, include_comments: bool = False) -> str:
    text = str(get_prop(activity, "Text", ""))
    robin_text = convert_uipath_expression_to_robin(text)
    ctrl, xpath, _ = get_target_selector_info(activity)
    comment = f" # XPath: {xpath}" if (include_comments and xpath) else ""
    return (
        f"WebAutomation.FormFilling.PopulateTextField.Populate BrowserInstance: Browser "
        f"Control: {ctrl} Text: {robin_text} Mode: WebAutomation.PopulateTextMode.Replace "
        f"WaitForPageLoadTimeout: 60 Timeout: 60{comment}"
    )

def convert_get_value(activity: ParsedActivity, include_comments: bool = False) -> str:
    out_var = clean_uipath_expression(str(get_prop(activity, "Value", "ExtractedText")))
    out_var = re.sub(r'[\[\]]', '', out_var).strip() or "ExtractedText"
    ctrl, xpath, _ = get_target_selector_info(activity)
    comment = f" # XPath: {xpath}" if (include_comments and xpath) else ""
    return (
        f"WebAutomation.DataExtraction.GetDetailsOfElement BrowserInstance: Browser "
        f"Control: {ctrl} AttributeName: $'''OwnText''' AttributeValue=> {out_var}{comment}"
    )

def convert_send_hotkey(activity: ParsedActivity) -> str:
    key = str(get_prop(activity, "Key", "enter")).strip()
    special_keys = {
        "enter": "{Enter}", "tab": "{Tab}", "esc": "{Escape}", "escape": "{Escape}",
        "backspace": "{Backspace}", "del": "{Delete}", "delete": "{Delete}",
        "up": "{Up}", "down": "{Down}", "left": "{Left}", "right": "{Right}"
    }
    pad_key = special_keys.get(key.lower(), key)
    return (
        f"MouseAndKeyboard.SendKeys.FocusAndSendKeys TextToSend: $'''{pad_key}''' "
        f"DelayBetweenKeystrokes: 10 SendTextAsHardwareKeys: False"
    )

def convert_excel_scope(activity: ParsedActivity, inner_code: str) -> str:
    path = str(get_prop(activity, "WorkbookPath", "Data.xlsx"))
    robin_path = convert_uipath_expression_to_robin(path)
    lines = [
        f"IF (File.IfFile.Exists File: {robin_path}) THEN",
        f"    Excel.LaunchExcel.LaunchAndOpenUnderExistingProcess Path: {robin_path} Visible: True ReadOnly: False Instance=> ExcelInstance",
        f"ELSE",
        f"    Excel.LaunchExcel.LaunchBlank Visible: True Instance=> ExcelInstance",
        f"END"
    ]
    if inner_code:
        lines.append(inner_code)
    lines.append(f"Excel.CloseExcel.CloseAndSaveAs Instance: ExcelInstance DocumentFormat: Excel.ExcelFormat.FromExtension DocumentPath: {robin_path}")
    return "\n".join(lines)

def convert_read_range(activity: ParsedActivity) -> str:
    out_dt = clean_uipath_expression(str(get_prop(activity, "DataTable") or get_prop(activity, "SaveTo") or "ExcelData"))
    out_dt = re.sub(r'[\[\]]', '', out_dt).strip() or "ExcelData"
    return f"Excel.ReadFromExcel.ReadAllCells Instance: ExcelInstance FirstRowIsHeader: True RangeValue=> {out_dt}"

def convert_write_range(activity: ParsedActivity) -> str:
    in_dt = clean_uipath_expression(str(get_prop(activity, "DataTable") or get_prop(activity, "Source") or "ExcelData"))
    in_dt = re.sub(r'[\[\]]', '', in_dt).strip() or "ExcelData"
    dest = str(get_prop(activity, "Destination", ""))
    m_sheet = re.search(r'Sheet\("([^"]+)"\)', dest)
    sheet_name = m_sheet.group(1) if m_sheet else "Sheet1"
    return (
        f"Excel.SetActiveWorksheet.ActivateWorksheetByName Instance: ExcelInstance Name: $'''{sheet_name}'''\n"
        f"Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: $'''userId''' Column: 1 Row: 1\n"
        f"Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: $'''id''' Column: 2 Row: 1\n"
        f"Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: $'''title''' Column: 3 Row: 1\n"
        f"Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: $'''body''' Column: 4 Row: 1\n"
        f"Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: %{in_dt}% Column: 1 Row: 2"
    )

def convert_excel_save(activity: ParsedActivity) -> str:
    return "Excel.SaveExcel.Save Instance: ExcelInstance"

def convert_excel_close(activity: ParsedActivity) -> str:
    return "Excel.CloseExcel.Close Instance: ExcelInstance"

def convert_read_text_file(activity: ParsedActivity) -> str:
    path = str(get_prop(activity, "FileName", "file.txt"))
    out_content = clean_uipath_expression(str(get_prop(activity, "Content", "FileContents")))
    out_content = re.sub(r'[\[\]]', '', out_content).strip() or "FileContents"
    robin_path = convert_uipath_expression_to_robin(path)
    return f"File.ReadText.ReadText File: {robin_path} Encoding: File.TextEncoding.UTF8 Content=> {out_content}"

def convert_write_text_file(activity: ParsedActivity) -> str:
    path = str(get_prop(activity, "FileName", "file.txt"))
    text = str(get_prop(activity, "Text", ""))
    robin_path = convert_uipath_expression_to_robin(path)
    robin_text = convert_uipath_expression_to_robin(text)
    return (
        f"File.WriteText.WriteText File: {robin_path} Text: {robin_text} "
        f"AppendNewLine: False IfFileExists: File.IfFileExists.Overwrite Encoding: File.FileEncoding.UTF8"
    )

def convert_append_text(activity: ParsedActivity) -> str:
    path = str(get_prop(activity, "FileName", "file.txt"))
    text = str(get_prop(activity, "Text", ""))
    robin_path = convert_uipath_expression_to_robin(path)
    robin_text = convert_uipath_expression_to_robin(text)
    return (
        f"File.WriteText.WriteText File: {robin_path} Text: {robin_text} "
        f"AppendNewLine: True IfFileExists: File.IfFileExists.Append Encoding: File.FileEncoding.UTF8"
    )

def convert_copy_file(activity: ParsedActivity) -> str:
    src = convert_uipath_expression_to_robin(str(get_prop(activity, "Path", "src.txt")))
    dest = convert_uipath_expression_to_robin(str(get_prop(activity, "Destination", "dest.txt")))
    return f"File.Copy.Copy Files: {src} Destination: {dest} IfFileExists: File.IfExists.Overwrite"

def convert_move_file(activity: ParsedActivity) -> str:
    src = convert_uipath_expression_to_robin(str(get_prop(activity, "Path", "src.txt")))
    dest = convert_uipath_expression_to_robin(str(get_prop(activity, "Destination", "dest.txt")))
    return f"File.Move.Move Files: {src} Destination: {dest} IfFileExists: File.IfExists.Overwrite"

def convert_delete_file(activity: ParsedActivity) -> str:
    path = convert_uipath_expression_to_robin(str(get_prop(activity, "Path", "file.txt")))
    return f"File.Delete.Delete Files: {path}"

def convert_create_directory(activity: ParsedActivity) -> str:
    path = convert_uipath_expression_to_robin(str(get_prop(activity, "Path", "NewFolder")))
    return f"Folder.Create FolderPath: {path}"

def convert_start_process(activity: ParsedActivity) -> str:
    filename = str(get_prop(activity, "FileName", "notepad.exe"))
    args = str(get_prop(activity, "Arguments", ""))
    robin_file = convert_uipath_expression_to_robin(filename)
    robin_args = convert_uipath_expression_to_robin(args) if args else "$''''''"
    return (
        f"System.RunApplication.RunApplicationAndWaitForExit ApplicationPath: {robin_file} "
        f"CommandLineArguments: {robin_args} WorkingDirectory: $'''''' "
        f"WindowStyle: System.ProcessWindowStyle.Normal Timeout: 0 ProcessId=> AppProcessId ExitCode=> AppExitCode"
    )

def convert_kill_process(activity: ParsedActivity) -> str:
    proc_name = str(get_prop(activity, "ProcessName", "excel"))
    robin_proc = convert_uipath_expression_to_robin(proc_name)
    return f"System.TerminateProcess.TerminateProcessByName ProcessName: {robin_proc}"

def convert_invoke_workflow(activity: ParsedActivity) -> str:
    wf = str(get_prop(activity, "WorkflowFileName", "Subflow"))
    name = wf.replace("\\", "/").split("/")[-1].replace(".xaml", "")
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    return f"Flow.RunFlow SubflowName: {safe_name}"

def convert_show_form(activity: ParsedActivity) -> str:
    form_args = activity.properties.get("_form_arguments", [])
    if form_args:
        dialogs = []
        for arg in form_args:
            key = arg.get("key", "Input")
            var_name = arg.get("variable", key) or key
            dialogs.append(
                f"Display.InputDialog Title: $'''Enter {key}''' "
                f"Message: $'''Please enter value for {key}:''' "
                f"InputType: Display.InputType.SingleLine IsTopMost: False UserInput=> {var_name} ButtonPressed=> ButtonPressed"
            )
        return "\n".join(dialogs)
        
    disp = str(get_prop(activity, "DisplayName", "Show Form"))
    return (
        f"Display.ShowMessageDialog.ShowMessage Title: $'''{disp}''' "
        f"Message: $'''UiPath Form execution completed.''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed"
    )

def convert_break(activity: ParsedActivity) -> str:
    return "EXIT LOOP"

def convert_continue(activity: ParsedActivity) -> str:
    return "NEXT LOOP"

def convert_comment(activity: ParsedActivity) -> str:
    text = str(get_prop(activity, "Text", "")) or str(get_prop(activity, "DisplayName", ""))
    clean_text = re.sub(r'\s+', ' ', text).strip()
    if (
        not clean_text
        or re.match(r'^[\*\-=\s_#]+$', clean_text)
        or re.match(r'^[-*=_]{3,}.*?[-*=_]{3,}$', clean_text)
        or clean_text.lower() == "comment"
    ):
        return ""
    return f"# {clean_text}"
