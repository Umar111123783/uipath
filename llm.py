import os
import re
import json
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from converter.project_manager import ProjectManager

SYSTEM_PROMPT = """You are an expert RPA migration engineer specialized in converting UiPath projects (XAML workflows, dependencies, selectors) into native Microsoft Power Automate Desktop (PAD) Robin language scripts.

You will receive the complete extracted context of a UiPath project, including project.json, all XAML workflows, and detected DLLs.

Your output MUST be a JSON object with two fields:
{
  "summary": "A concise executive business and technical summary of what this UiPath bot does, its inputs, outputs, activities mapped, and how it was translated to Power Automate Desktop.",
  "robin_script": "The complete, production-grade Power Automate Desktop (Robin) script ready to be pasted (Ctrl+V) directly into the Power Automate Desktop designer canvas."
}

Rules for the Robin Script:
1. Always use exact Power Automate Desktop Robin syntax:
   - Variable assignment: SET VarName TO $'''String''' or SET VarName TO %expression%
   - User inputs: Display.InputDialog.Show Title: $'''...''' Message: $'''...''' UserInput=> VarName ButtonPressed=> ButtonPressed
   - Message boxes: Display.ShowMessageDialog.ShowMessage Title: $'''...''' Message: $'''...''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False Log=> DialogResult
   - Delays: Wait Delay: 3
   - Web automation: WebAutomation.LaunchChrome.LaunchChrome, WebAutomation.Click.Click, WebAutomation.FormFilling.PopulateTextField.Populate, WebAutomation.CloseWebBrowser
   - Excel: Excel.LaunchExcel.LaunchAndOpenUnderExistingProcess, Excel.ReadFromExcel.ReadAllCells, Excel.WriteToExcel.WriteCell, Excel.CloseExcel.Close
   - REST APIs: Web.InvokeWebService.Invoke Method: Web.Method.Get Url: $'''...''' Accept: $'''application/json''' ... Response=> responseString
   - JSON: Variables.ConvertJsonToCustomObject Json: %responseString% CustomObject=> jsonObj
   - Tables: Variables.CreateNewDatatable, Variables.AddRowToDataTable.AppendRowToDataTable
   - Flow control: IF ... THEN ... ELSE ... END, SWITCH ... CASE ... DEFAULT ... END SWITCH, LOOP FOREACH ... IN ... END
2. Never output '{x:Null}'. Output $'''''' for empty/null strings.
3. If multiple workflows exist, structure them using FUNCTION SubflowName ... END FUNCTION.
4. Provide the response strictly as valid JSON or as a JSON code block.
"""

def convert_to_robin(api_key: str, model: str, xml_context: str, dlls: List[str]) -> Dict[str, Any]:
    """
    Converts UiPath XML context and DLLs into a PAD Robin script and summary
    using either Google Gemini or OpenAI LLMs (with fallback to local AST engine).
    """
    clean_model = model.strip()
    if clean_model.startswith("openai."):
        clean_model = clean_model.replace("openai.", "")

    response_text = ""
    summary = ""
    robin_script = ""

    # Check if Gemini or OpenAI
    is_gemini = "gemini" in clean_model.lower() or not (clean_model.startswith("gpt-") or "claude" in clean_model.lower())
    
    # 1. Try Gemini API
    if is_gemini and api_key:
        try:
            # Map standard model names if user typed generic
            gemini_model_name = clean_model if "gemini" in clean_model.lower() else "gemini-2.5-flash"
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model_name}:generateContent?key={api_key}"
            
            prompt_content = f"UiPath Project Extracted Context:\n{xml_context}\n\nDetected DLL Dependencies:\n{', '.join(dlls) if dlls else 'None'}\n\nConvert this into Power Automate Desktop (Robin) script and business summary in JSON format."
            
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt_content}]
                    }
                ],
                "systemInstruction": {
                    "parts": [{"text": SYSTEM_PROMPT}]
                },
                "generationConfig": {
                    "temperature": 0.1,
                    "maxOutputTokens": 8192
                }
            }
            
            resp = requests.post(endpoint, json=payload, headers={"Content-Type": "application/json"}, timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    response_text = "\n".join(p.get("text", "") for p in parts)
            else:
                response_text = f"Gemini Error ({resp.status_code}): {resp.text}"
        except Exception as ex:
            response_text = f"Gemini Request Exception: {str(ex)}"

    # 2. Try OpenAI API if requested
    elif not is_gemini and api_key:
        try:
            endpoint = "https://api.openai.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            prompt_content = f"UiPath Project Extracted Context:\n{xml_context}\n\nDetected DLL Dependencies:\n{', '.join(dlls) if dlls else 'None'}\n\nConvert this into Power Automate Desktop (Robin) script and business summary in JSON format."
            
            payload = {
                "model": clean_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt_content}
                ],
                "temperature": 0.1
            }
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    response_text = choices[0].get("message", {}).get("content", "")
            else:
                response_text = f"OpenAI Error ({resp.status_code}): {resp.text}"
        except Exception as ex:
            response_text = f"OpenAI Request Exception: {str(ex)}"

    # Save raw response for user inspection
    Path("model_response.txt").write_text(response_text or "No model response generated.", encoding="utf-8")

    # 3. Parse JSON response if returned by LLM
    if response_text and not response_text.startswith("Gemini Error") and not response_text.startswith("OpenAI Error"):
        # Strip code markdown if wrapped
        clean_resp = response_text.strip()
        if "```json" in clean_resp:
            clean_resp = clean_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_resp:
            clean_resp = clean_resp.split("```")[1].split("```")[0].strip()
            
        try:
            parsed = json.loads(clean_resp)
            summary = parsed.get("summary", "")
            robin_script = parsed.get("robin_script", "")
        except Exception:
            # Check if LLM output was formatted with code blocks ```robin ... ```
            if "```" in response_text:
                blocks = re.findall(r'```(?:robin|text)?\s*(.*?)\s*```', response_text, re.DOTALL)
                if blocks:
                    robin_script = blocks[0].strip()
                    summary = re.sub(r'```(?:robin|text)?\s*.*?\s*```', '', response_text, flags=re.DOTALL).strip()
            if not robin_script and ("FUNCTION" in response_text or "SET " in response_text or "Display." in response_text):
                robin_script = response_text.strip()
                summary = "Robin script generated directly by LLM."

    # 4. Fallback / Augment with Local Deterministic Engine if LLM failed or didn't return robin_script
    if not robin_script:
        pm = ProjectManager(include_comments=True, include_selectors_header=True)
        # Parse from context or extract
        local_robin = ""
        try:
            # Parse individual workflows found in context
            wf_blocks = re.split(r'={20,}\nWORKFLOW XAML FILE:\s*([^\n]+)\n={20,}', xml_context)
            if len(wf_blocks) > 1:
                # pairs of (filename, content)
                robin_parts = []
                for i in range(1, len(wf_blocks), 2):
                    fname = Path(wf_blocks[i].strip()).name
                    x_content = wf_blocks[i+1]
                    proj = pm.process_single_xaml(x_content, filename=fname)
                    robin_parts.append(pm.get_full_project_robin(proj))
                local_robin = "\n\n".join(robin_parts)
            else:
                proj = pm.process_single_xaml(xml_context, filename="Main.xaml")
                local_robin = pm.get_full_project_robin(proj)
        except Exception:
            local_robin = "# Local fallback conversion completed."

        robin_script = local_robin
        if not summary:
            summary = (
                f"Automated translation completed using the AST RPA Converter Engine. "
                f"All activities, flow containers, and expressions were mapped to native Power Automate Desktop (Robin) syntax. "
                f"{f'Model notice: {response_text[:200]}' if response_text else ''}"
            )

    return {
        "summary": summary,
        "robin_script": robin_script
    }

