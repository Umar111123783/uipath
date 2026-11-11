import re
import json
import time
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from parser import (
    apply_robin_node_metadata,
    extract_robin_metadata_context,
    sanitize_robin_script,
)

SYSTEM_PROMPT = """You are an expert RPA migration engineer specialized in converting UiPath projects (XAML workflows, dependencies, selectors) into native Microsoft Power Automate Desktop (PAD) Robin language scripts.

You will receive the complete extracted context of a UiPath project, including project.json, all XAML workflows, and detected DLLs.

Your output MUST be a JSON object with two fields:
{
  "summary": "A concise executive business and technical summary of what this UiPath bot does, its inputs, outputs, activities mapped, and how it was translated to Power Automate Desktop.",
  "robin_script": "The complete, clean Power Automate Desktop (Robin) script ready to be pasted (Ctrl+V) directly into the Power Automate Desktop designer canvas."
}

CRITICAL RULES FOR POWER AUTOMATE DESKTOP (ROBIN) CANVAS PASTE SYNTAX:
1. CLEAN CANVAS PASTE FORMAT (NO HEADERS, DEBUG COMMENTS, OR FUNCTION MAIN):
   - For direct Ctrl+V pasting into the PAD designer canvas, do NOT wrap the main flow in 'FUNCTION Main ... END FUNCTION'. Output top-level bare action lines sequentially.
   - Subflows (if any other than Main exist) may be appended at the bottom using 'FUNCTION SubflowName ... END FUNCTION'.
   - Do NOT emit header banners ('# POWER AUTOMATE DESKTOP...', '# Project:...', '# Instructions:...'), '# node_id=...' metadata lines, '# Converted from...', or decorative '# ====' / '# ****' / '# ---' divider comments (such as '# --- Initialize Variables ---').
   - Only emit '# ...' lines for genuine Comment or Log activities from the source bot (every '#' line becomes a Comment action on the PAD canvas).
   - Do NOT output markdown fences or blank lines inside blocks.
   - Output PLAIN TEXT Robin syntax ONLY: NEVER HTML-encode characters (never output '&gt;', '&lt;', '&amp;', '&quot;', or '=&gt;'; use raw '>', '<', '&', '"', '=>'), and NEVER wrap URLs in HTML '<a href=...>...</a>' tags or Markdown '[url](url)' links.

2. EXACT NATIVE PAD ACTION IDENTIFIERS:
   - Web service: Web.InvokeWebService.InvokeWebService Url: $'''...''' Method: Web.Method.Get Accept: $'''application/json''' ContentType: $'''application/json''' ConnectionTimeout: 30 FollowRedirection: True ClearCookies: False FailOnErrorStatus: False EncodeRequestBody: True UserAgent: $'''Mozilla/5.0''' Encoding: Web.Encoding.AutoDetect AcceptUntrustedCertificates: False ResponseHeaders=> ResponseHeaders Response=> responseString StatusCode=> responseStatus
   - Messages: Display.ShowMessageDialog.ShowMessage Title: $'''...''' Message: $'''...''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed
   - Inputs: Display.InputDialog Title: $'''...''' Message: $'''...''' InputType: Display.InputType.SingleLine IsTopMost: False UserInput=> VarName ButtonPressed=> ButtonPressed
   - Convert text to number: Text.ToNumber Text: SourceTextVar Number=> TargetNumVar
   - Delays: Wait Delay: 2 (delay in seconds, never WAIT TODO_DURATION)
   - Stop execution on critical failure: FlowControl.StopFlow Execution: FlowControl.StopFlowMode.StopNormally
   - Create DataTable: Variables.CreateNewDatatable InputTable: { ^['Col1', 'Col2'] } DataTable=> dtPosts
   - Insert DataRow: Variables.AddRowToDataTable.AppendRowToDataTable DataTable: dtPosts RowToAdd: [CurrentItem['col1'], CurrentItem['col2']]
   - Folder paths: Folder.GetSpecialFolder SpecialFolder: Folder.SpecialFolder.DesktopDirectory SpecialFolderPath=> SpecialFolderPath

3. SINGLE LINE PER ACTION & NEWLINES:
   - Every action statement MUST be strictly on a SINGLE CONTIGUOUS LINE.
   - Never insert a physical line break inside an action or inside a string parameter. For newlines in dialogs, use '\\r\\n' escape characters.

4. CONTROL FLOW, INDENTATION & CLEAN BLOCKS:
   - Every IF statement MUST have a matching END statement (IF ... THEN ... ELSE ... END).
   - Every LOOP statement MUST have a matching END statement.
   - Use consistent 4-space indentation inside IF / ELSE IF / ELSE / END, LOOP / END, and SWITCH blocks, with no blank lines inside blocks.

5. VARIABLE SYNTAX & NUMERIC CONVERSION OF TEXT INPUTS:
   - Reference bare variable names in SET, Text:, and IF/LOOP conditions (e.g. SET x TO $''''''', IF count >= 10 THEN), and %VarName% only for string interpolation inside $'''...''' literals (NEVER Automation Anywhere $Var$ or .NET constructors).
   - Initialize strings: SET VarName TO $''''''
   - Display.InputDialog always outputs a Text variable. Whenever an InputDialog or string variable is used in a numeric comparison (>=, >, <, <=) or numeric cast (CInt, Convert.ToInt32, CDbl), convert it first with Text.ToNumber and guard with ButtonPressed = $'''OK''':
     Display.InputDialog Title: $'''Age Checker''' Message: $'''Please enter your age''' InputType: Display.InputType.SingleLine IsTopMost: False UserInput=> userAgeText ButtonPressed=> ButtonPressed
     IF ButtonPressed = $'''OK''' THEN
         Text.ToNumber Text: userAgeText Number=> userAgeText_Num
         IF userAgeText_Num >= 18 THEN
             Display.ShowMessageDialog.ShowMessage Title: $'''Message''' Message: $'''You are an adult''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed
         ELSE
             Display.ShowMessageDialog.ShowMessage Title: $'''Message''' Message: $'''You are a Minor''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed
         END
     END
   - Initialize JSON objects: Variables.ConvertJsonToCustomObject Json: $'''{}''' CustomObject=> jsonObj
   - Initialize lists/arrays: Variables.CreateNewList List=> jsonArray

6. REST APIS & CRITICAL ERROR HANDLING:
   - Extract URLs from EndPoint or RequestUrl (e.g. Url: $'''https://jsonplaceholder.typicode.com/posts/%delPostId%''').
   - Method accuracy: When updating an existing post with a JSON request body, use Method: Web.Method.Put (never GET). For deleting, use Web.Method.Delete. For creating, use Web.Method.Post.
   - Response validation & Stop flow on critical errors:
     IF responseStatus < 200 OR responseStatus >= 300 THEN
         Display.ShowMessageDialog.ShowMessage Title: $'''API Error''' Message: $'''HTTP request failed with status: %responseStatus%\\r\\n%responseString%''' Icon: Display.Icon.Error Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed
         FlowControl.StopFlow Execution: FlowControl.StopFlowMode.StopNormally
     END

7. EXCEL WORKBOOK & WORKSHEET SETUP:
   - Ensure the workbook file exists or create a blank one:
     IF (File.IfFile.Exists File: %excelPath%) THEN
         Excel.LaunchExcel.LaunchAndOpenUnderExistingProcess Path: %excelPath% Visible: True ReadOnly: False Instance=> ExcelInstance
     ELSE
         Excel.LaunchExcel.LaunchBlank Visible: True Instance=> ExcelInstance
     END
   - Explicitly activate the worksheet: Excel.SetActiveWorksheet.ActivateWorksheetByName Instance: ExcelInstance Name: $'''Sheet1'''
   - Write headers and rows, then save and close:
     Excel.CloseExcel.CloseAndSaveAs Instance: ExcelInstance DocumentFormat: Excel.ExcelFormat.FromExtension DocumentPath: %excelPath%
"""

def _parse_llm_response(
    response_text: str,
    include_node_metadata: bool = False,
    workflow_name: str = "Workflow",
    var_types: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Extract (summary, sanitized_robin_script) from raw LLM text output."""
    if not response_text:
        return "", ""

    summary = ""
    robin_script: Any = ""

    clean_resp = response_text.strip()
    if "```json" in clean_resp:
        clean_resp = clean_resp.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in clean_resp:
        clean_resp = clean_resp.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        parsed = json.loads(clean_resp)
        if isinstance(parsed, dict):
            summary = str(parsed.get("summary", ""))
            robin_script = parsed.get("robin_script", "")
    except Exception:
        if "```" in response_text:
            blocks = re.findall(r'```(?:robin|text)?\s*(.*?)\s*```', response_text, re.DOTALL)
            if blocks:
                robin_script = blocks[0].strip()
                summary = re.sub(r'```(?:robin|text)?\s*.*?\s*```', '', response_text, flags=re.DOTALL).strip()
        if not robin_script and (
            "FUNCTION " in response_text
            or "SET " in response_text
            or "Display." in response_text
            or "IF " in response_text
        ):
            robin_script = response_text.strip()
            summary = "Robin script generated directly by LLM."

    if isinstance(robin_script, (list, dict)):
        robin_script = json.dumps(robin_script, indent=2, ensure_ascii=False)

    cleaned = sanitize_robin_script(
        str(robin_script or ""),
        keep_node_metadata=False,
        preserve_blank_lines=False,
    )
    if cleaned and include_node_metadata:
        cleaned = apply_robin_node_metadata(
            cleaned,
            workflow_name=workflow_name,
            var_types=var_types,
            reset_per_subflow=True,
        )
        cleaned = sanitize_robin_script(
            cleaned,
            keep_node_metadata=True,
            preserve_blank_lines=True,
        )
    return summary, cleaned


def _call_gemini(
    api_key: str,
    clean_model: str,
    prompt_content: str,
    temperature: float,
) -> Tuple[str, Optional[str], str]:
    """Execute Gemini request with cluster failover; returns (response_text, error_message, used_model)."""
    initial_model = clean_model if "gemini" in clean_model.lower() else "gemini-2.0-flash"
    if "gemini-2.5" in initial_model:
        initial_model = "gemini-2.0-flash"

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt_content}]}],
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 8192},
    }

    models_to_try = [initial_model]
    for candidate in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-3.8-flash"]:
        if candidate not in models_to_try:
            models_to_try.append(candidate)

    response_text = ""
    error_message: Optional[str] = None
    used_model = initial_model

    for current_m in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{current_m}:generateContent?key={api_key}"
        try:
            resp = requests.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=120,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    response_text = "\n".join(p.get("text", "") for p in parts)
                used_model = current_m
                error_message = None
                break
            if resp.status_code in (503, 429):
                error_message = f"Gemini Error ({resp.status_code}): {resp.text}"
                time.sleep(1.2)
                continue
            if resp.status_code == 404:
                error_message = f"Gemini Error (404): {resp.text}"
                continue
            error_message = f"Gemini Error ({resp.status_code}): {resp.text}"
            break
        except requests.RequestException as ex:
            error_message = f"Gemini Request Exception: {str(ex)}"
            continue

    return response_text, error_message, used_model


def _call_openai(
    api_key: str,
    clean_model: str,
    prompt_content: str,
    temperature: float,
) -> Tuple[str, Optional[str], str]:
    """Execute OpenAI chat completions request; returns (response_text, error_message, used_model)."""
    endpoint = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": clean_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_content},
        ],
        "temperature": temperature,
    }
    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            text = choices[0].get("message", {}).get("content", "") if choices else ""
            return text, None, clean_model
        return "", f"OpenAI Error ({resp.status_code}): {resp.text}", clean_model
    except Exception as ex:
        return "", f"OpenAI Request Exception: {str(ex)}", clean_model


def convert_to_robin(
    api_key: str,
    model: str,
    xml_context: str,
    dlls: List[str],
    temperature: float = 0.1,
    include_node_metadata: bool = False,
) -> Dict[str, Any]:
    """
    Convert UiPath XML context and DLLs into a clean PAD Robin script and summary
    strictly using an LLM call (Google Gemini or OpenAI), with no local AST fallback.
    """
    clean_model = model.strip()
    if clean_model.startswith("openai."):
        clean_model = clean_model.replace("openai.", "", 1)

    if not api_key or not api_key.strip():
        return {
            "success": False,
            "summary": "",
            "robin_script": "",
            "engine": "LLM",
            "error": "API Key is required for LLM conversion.",
            "raw_response": "",
            "model_used": clean_model,
        }

    prompt_content = (
        f"UiPath Project Extracted Context:\n{xml_context}\n\n"
        f"Detected DLL Dependencies:\n{', '.join(dlls) if dlls else 'None'}\n\n"
        "Convert this into clean, directly pasteable Power Automate Desktop (Robin) script and business summary in JSON format."
    )

    is_gemini = "gemini" in clean_model.lower() or not (
        clean_model.startswith("gpt-") or "claude" in clean_model.lower()
    )

    if is_gemini:
        response_text, error_message, used_model = _call_gemini(
            api_key, clean_model, prompt_content, temperature
        )
    else:
        response_text, error_message, used_model = _call_openai(
            api_key, clean_model, prompt_content, temperature
        )

    Path("model_response.txt").write_text(
        response_text or error_message or "No model response generated.",
        encoding="utf-8",
    )

    if not response_text:
        return {
            "success": False,
            "summary": "",
            "robin_script": "",
            "engine": "LLM",
            "error": error_message or "No response received from the AI model.",
            "raw_response": error_message or "",
            "model_used": used_model,
        }

    workflow_name, var_types = extract_robin_metadata_context(xml_context)
    summary, robin_script = _parse_llm_response(
        response_text,
        include_node_metadata=include_node_metadata,
        workflow_name=workflow_name,
        var_types=var_types,
    )
    if not robin_script:
        return {
            "success": False,
            "summary": summary,
            "robin_script": "",
            "engine": "LLM",
            "error": "The LLM responded, but did not return a valid Robin script.",
            "raw_response": response_text,
            "model_used": used_model,
        }

    return {
        "success": True,
        "summary": summary,
        "robin_script": robin_script,
        "engine": "LLM",
        "error": None,
        "raw_response": response_text,
        "model_used": used_model,
    }

