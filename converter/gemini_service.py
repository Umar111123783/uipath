import os
import json
import requests
from typing import List, Dict, Optional, Tuple, Any

AVAILABLE_DEFAULT_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash"
]

SYSTEM_PROMPT = """You are an elite RPA automation engineer specializing in converting UiPath automation bots (XAML workflows) into native Microsoft Power Automate Desktop (PAD) Robin scripts.

Your objective:
Convert the provided UiPath XAML workflow or activity sequence into clean, valid, native Power Automate Desktop (Robin) script that can be directly pasted (Ctrl+V) into the Power Automate Desktop flow designer canvas.

Key Rules for Robin Script Output:
1. Always use exact Power Automate Desktop action syntax:
   - Variables: `SET VariableName TO $'''StringLiteral'''` or `SET VariableName TO %expression%`
   - Messages: `Display.ShowMessageDialog.ShowMessage Title: $'''Title''' Message: $'''Text''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False Log=> DialogResult`
   - Inputs: `Display.InputDialog.Show Title: $'''Title''' Message: $'''Label''' InputType: Display.InputType.SingleLine IsTopMost: False UserInput=> VarName ButtonPressed=> ButtonPressed`
   - Web: `WebAutomation.LaunchChrome.LaunchChrome Url: $'''url''' WindowState: WebAutomation.WindowState.Normal ClearCache: False ClearCookies: False WaitForPageLoadTimeout: 60 Timeout: 60 BrowserInstance=> Browser`
   - Web Click: `WebAutomation.Click.Click BrowserInstance: Browser Control: appmask['UIElement'] ClickType: WebAutomation.ClickType.LeftClick MouseClick: False WaitForPageLoadTimeout: 60 Timeout: 60`
   - Web Input: `WebAutomation.FormFilling.PopulateTextField.Populate BrowserInstance: Browser Control: appmask['UIElement'] Text: $'''text''' Mode: WebAutomation.PopulateTextMode.Replace WaitForPageLoadTimeout: 60 Timeout: 60`
   - Excel: `Excel.LaunchExcel.LaunchAndOpenUnderExistingProcess Path: $'''path''' Visible: True ReadOnly: False Instance=> ExcelInstance`
   - Excel Read: `Excel.ReadFromExcel.ReadAllCells Instance: ExcelInstance FirstRowIsHeader: True RangeValue=> dtData`
   - Excel Write: `Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: %dtData% Column: 1 Row: 1`
   - Excel Close: `Excel.CloseExcel.Close Instance: ExcelInstance`
   - Web Service (REST API): `Web.InvokeWebService.Invoke Method: Web.Method.Get Url: $'''url''' Accept: $'''application/json''' ContentType: $'''application/json''' ConnectionTimeout: 30 FollowRedirection: True ClearCookies: False StatusCode=> responseStatus ResponseHeaders=> ResponseHeaders Response=> responseString`
   - JSON: `Variables.ConvertJsonToCustomObject Json: %responseString% CustomObject=> jsonObj`
   - Tables: `Variables.CreateNewDatatable Columns: 4 Rows: 0 DataTable=> dtTable`
   - Append Row: `Variables.AddRowToDataTable.AppendRowToDataTable DataTable: dtTable RowToInsert: [val1, val2]`
   - Loops: `LOOP FOREACH CurrentItem IN %collection%` ... `END`
   - Conditions: `IF condition THEN` ... `ELSE` ... `END`
   - Switches: `SWITCH %var%` ... `CASE $'''val'''` ... `DEFAULT` ... `END SWITCH`
   - Delays: `Wait Delay: 5`
   - Files: `File.ReadText.ReadText`, `File.WriteText.WriteText`, `File.Copy.Copy`, `Folder.Create`
2. Never output `{x:Null}`. Convert null or empty values to `$''''''`.
3. If outputting a subflow or main workflow, wrap in `FUNCTION Main` ... `END FUNCTION` or output clean actions.
4. Output ONLY the Robin script inside a ```robin ... ``` code block, followed by a brief summary of activities converted.
"""

class GeminiService:
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.model = model

    def validate_key(self) -> Tuple[bool, str]:
        """Test API key by querying available models or a test generation."""
        if not self.api_key:
            return False, "API key is empty. Please enter your Gemini API key."
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                model_count = len(data.get("models", []))
                return True, f"Connected successfully! {model_count} models available."
            elif resp.status_code == 400:
                return False, f"Invalid API Key: {resp.text}"
            else:
                return False, f"API Error ({resp.status_code}): {resp.text}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def list_available_models(self) -> List[str]:
        """Fetch list of supported generation models for this key."""
        if not self.api_key:
            return AVAILABLE_DEFAULT_MODELS
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                found = []
                for m in data.get("models", []):
                    name = m.get("name", "").replace("models/", "")
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods and "gemini" in name.lower():
                        found.append(name)
                if found:
                    return found
        except Exception:
            pass
        return AVAILABLE_DEFAULT_MODELS

    def convert_xaml_with_gemini(
        self,
        xaml_content: str,
        workflow_name: str = "Main.xaml",
        few_shot_examples: Optional[List[Dict[str, Any]]] = None,
        custom_instructions: str = ""
    ) -> Tuple[str, Dict[str, Any]]:
        """Call Gemini to convert a single UiPath XAML workflow into Robin script."""
        if not self.api_key:
            raise ValueError("Gemini API key is required. Please enter your API key in the UI.")

        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        # Build prompt with few-shot context if available
        user_prompt_parts = []
        user_prompt_parts.append(f"Convert this UiPath workflow ({workflow_name}) to Microsoft Power Automate Desktop (Robin) script:\n")
        
        if few_shot_examples:
            user_prompt_parts.append("### Relevant Reference Pairs from Training Dataset:")
            for eg in few_shot_examples[:5]:
                user_prompt_parts.append(f"- UiPath Activity: {eg.get('display_name', '')} ({eg.get('activity_type', '')})")
                user_prompt_parts.append(f"  Target Robin Action: {eg.get('robin_script', '')}")
            user_prompt_parts.append("\n")

        if custom_instructions:
            user_prompt_parts.append(f"### Additional User Instructions:\n{custom_instructions}\n")

        user_prompt_parts.append(f"### UiPath XAML Content:\n```xml\n{xaml_content}\n```")
        user_prompt = "\n".join(user_prompt_parts)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
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

        resp = requests.post(
            endpoint,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API returned error {resp.status_code}: {resp.text}")

        resp_data = resp.json()
        candidates = resp_data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"No response candidates returned: {resp_data}")

        parts = candidates[0].get("content", {}).get("parts", [])
        full_text = "\n".join(p.get("text", "") for p in parts)
        
        # Extract code block if wrapped in ```robin ... ``` or ``` ... ```
        robin_code = full_text
        if "```" in full_text:
            lines = full_text.split("\n")
            in_code = False
            code_lines = []
            for line in lines:
                if line.strip().startswith("```"):
                    in_code = not in_code
                    continue
                if in_code:
                    code_lines.append(line)
            if code_lines:
                robin_code = "\n".join(code_lines)

        metadata = {
            "model": self.model,
            "raw_response": full_text,
            "prompt_feedback": resp_data.get("promptFeedback", {}),
            "usage_metadata": resp_data.get("usageMetadata", {})
        }

        return robin_code, metadata

