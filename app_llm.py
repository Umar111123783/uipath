import os
import json
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st

from llm import (
    PROVIDER_PRESETS,
    convert_to_robin,
    is_local_endpoint,
)

from parser import (
    extract_zip,
    build_xml_context,
    get_dll_files,
    get_xaml_files,
    get_important_files,
    get_project_tree,
)


# ============================================================
# CONFIGURATION & DEFAULTS
# ============================================================

DEFAULT_ENDPOINT = (
    "https://genai-sharedservice-apac.pwcinternal.com/chat/completions"
)

DEFAULT_MODEL = "openai.global.gpt-4.1"

DEFAULT_ROBIN_REFERENCES = """
# ============================================================
# VERIFIED POWER AUTOMATE DESKTOP (PAD) ROBIN SIGNATURES
# ============================================================

# 1. VARIABLE INITIALIZATION & ASSIGNMENT
SET userAgeText TO $''''''
SET isSuccess TO True
SET counter TO 0

# 2. DIALOGS
Display.InputDialog Title: $'''Age Checker''' Message: $'''Please enter your age''' InputType: Display.InputType.SingleLine IsTopMost: False UserInput=> userAgeText ButtonPressed=> ButtonPressed
Display.ShowMessageDialog.ShowMessage Title: $'''Message''' Message: $'''Task completed''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed

# 3. TEXT & TYPE CONVERSION
Text.ToNumber Text: userAgeText Number=> userAgeText_Num

# 4. CONDITIONAL BRANCHING
IF userAgeText_Num >= 18 THEN
    Display.ShowMessageDialog.ShowMessage Title: $'''Message''' Message: $'''Adult''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed
ELSE
    Display.ShowMessageDialog.ShowMessage Title: $'''Message''' Message: $'''Minor''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed
END

# 5. EXCEL AUTOMATION
Excel.LaunchExcel.LaunchAndOpen Path: excelFilePath Visible: True LoadAddInsAndMacros: False Instance=> ExcelInstance
Excel.LaunchExcel.Launch Visible: True LoadAddInsAndMacros: False Instance=> ExcelInstance
Excel.ReadFromExcel.ReadAllCells Instance: ExcelInstance ReadAsText: False FirstLineIsHeader: True RangeValue=> customersTable
Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: $'''Processed''' Column: 5 Row: currentRow Index: 1
Excel.SaveExcel Instance: ExcelInstance
Excel.CloseExcel Instance: ExcelInstance

# 6. FILE & FOLDER AUTOMATION
Folder.Create FolderPath: backupFolder Folder=> CreatedFolder
Folder.GetSpecialFolder SpecialFolder: Folder.SpecialFolder.Desktop SpecialFolderPath=> DesktopPath
File.WriteText.WriteText File: backupFile TextToSend: fileContent Encoding: File.TextEncoding.UTF8 IfFileExists: File.IfFileExists.Overwrite
File.ReadTextFile File: sourceFile Encoding: File.TextEncoding.UTF8 Content=> fileContent
File.Copy Files: sourceFile Destination: destFolder IfFileExists: File.IfFileExists.Overwrite CopiedFiles=> CopiedFiles
File.Delete Files: oldFile

# 7. WEB AUTOMATION
WebAutomation.LaunchChrome.LaunchChrome Url: $'''https://www.google.com''' WindowState: WebAutomation.BrowserWindowState.Normal ClearCache: False ClearCookies: False BrowserInstance=> Browser
WebAutomation.CloseWebBrowser BrowserInstance: Browser

# 8. REST APIS & JSON
Web.InvokeWebService.InvokeWebService Url: $'''https://api.example.com/items''' Method: Web.Method.Post ContentType: $'''application/json''' RequestBody: reqBody ConnectionTimeout: 30 Output=> responseText StatusCode=> responseStatus
Variables.ConvertJsonToCustomObject Json: responseText CustomObject=> jsonObj
Variables.CreateNewList List=> jsonArray
Variables.CreateNewDatatable Columns: [$'''Col1''', $'''Col2'''] DataTable=> dtPosts

# 9. LOOPS
LOOP FOREACH CurrentRow IN %customersTable%
    # Loop body actions
END

# 10. SYSTEM & PROCESS
System.RunApplication.RunApplicationAndWaitForExit ApplicationPath: appPath CommandLineArguments: $'''''' WorkingDirectory: $'''''' WindowStyle: System.ProcessWindowStyle.Normal ProcessId=> ProcessId
System.TerminateProcess.TerminateProcessByName ProcessName: $'''notepad'''
WAIT 5
""".strip()


# ============================================================
# STREAMLIT PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="UiPath to PAD Robin Migration (AI Engine)",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 UiPath XAML → Power Automate Desktop Robin Converter")

st.caption(
    "AI-powered UiPath migration with built-in PAD Robin syntax verification "
    "and Canvas Pasteable output."
)


# ============================================================
# PROVIDER PRESETS
# ============================================================

PROVIDER_OPTIONS = {
    **PROVIDER_PRESETS,
    "PwC GenAI": {
        "endpoint": DEFAULT_ENDPOINT,
        "model": DEFAULT_MODEL,
    },
}


if "llm_preset" not in st.session_state:
    st.session_state["llm_preset"] = "PwC GenAI"

if "llm_endpoint" not in st.session_state:
    st.session_state["llm_endpoint"] = (
        os.environ.get("LLM_ENDPOINT", "").strip()
        or DEFAULT_ENDPOINT
    )

if "llm_model" not in st.session_state:
    st.session_state["llm_model"] = (
        os.environ.get("LLM_MODEL", "").strip()
        or DEFAULT_MODEL
    )

if "llm_api_key" not in st.session_state:
    st.session_state["llm_api_key"] = (
        os.environ.get("LLM_API_KEY", "")
        or os.environ.get("GEMINI_API_KEY", "")
        or os.environ.get("OPENAI_API_KEY", "")
    )

if "reference_examples" not in st.session_state:
    st.session_state["reference_examples"] = DEFAULT_ROBIN_REFERENCES


def apply_provider_preset():
    preset = PROVIDER_OPTIONS.get(
        st.session_state.get("llm_preset", ""),
        {},
    )
    st.session_state["llm_endpoint"] = preset.get("endpoint", "")
    st.session_state["llm_model"] = preset.get("model", "")


# ============================================================
# LLM EXECUTION
# ============================================================

def execute_pure_llm(
    api_key: str,
    model: str,
    xml_context: str,
    dlls: List[str],
    include_node_metadata: bool = False,
    temperature: float = 0.1,
    endpoint: str = "",
    reference_examples: str = "",
) -> Dict[str, Any]:
    """Execute migration through llm.py with reference examples."""
    return convert_to_robin(
        api_key=api_key,
        model=model,
        xml_context=xml_context,
        dlls=dlls,
        temperature=temperature,
        include_node_metadata=include_node_metadata,
        endpoint=endpoint,
        reference_examples=reference_examples,
    )


# ============================================================
# DISPLAY FUNCTIONS
# ============================================================

def display_action_mapping(mapping):
    st.subheader("📋 PAD Action Mapping")

    if not mapping:
        st.warning("No PAD action mapping was returned.")
        return

    display_rows = []
    for index, item in enumerate(mapping, start=1):
        display_rows.append({
            "No.": index,
            "Source Activity": item.get("source_activity", ""),
            "Source Type": item.get("source_activity_type", ""),
            "PAD Action": item.get("pad_action", ""),
            "Status": item.get("conversion_status", ""),
            "Description": item.get("description", ""),
            "Variables": ", ".join(
                item.get("variables", [])
                if isinstance(item.get("variables", []), list)
                else []
            ),
            "Notes": item.get("notes", ""),
        })

    st.dataframe(
        display_rows,
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("View Complete Action Mapping JSON"):
        st.json(mapping)

    st.download_button(
        label="Download Action Mapping JSON",
        data=json.dumps(mapping, indent=4, ensure_ascii=False),
        file_name="pad_action_mapping.json",
        mime="application/json",
    )


def display_robin_script(result: Dict[str, Any]):
    st.subheader("⚡ Generated Power Automate Desktop (Robin) Script")

    st.info(
        "💡 **How to Copy Without HTML Corruption (`<br>`, `&gt;`, `<a href>`):**\n"
        "1. Click inside the **Plain Text** box below and press **Ctrl + A → Ctrl + C**, "
        "or click **Download Robin Script (.txt)**.\n"
        "2. Open Power Automate Desktop and create or open your desktop flow.\n"
        "3. Click on the central flow designer canvas and press **Ctrl + V**."
    )

    robin_script = (result.get("robin_script") or "").strip()
    validation = result.get("robin_script_validation", {})

    if robin_script:
        status = validation.get("status", "ready")
        if status == "reference_aligned_unverified":
            st.warning(
                "Basic checks passed against reference signatures. "
                "Review actions before production execution."
            )
        elif status == "verified":
            st.success("✅ Robin syntax verification status: verified.")
        else:
            st.success("✅ Clean Robin script ready for PAD designer canvas.")

        st.text_area(
            "Plain Text Robin Script (Copy-Safe: Ctrl+A → Ctrl+C)",
            value=robin_script,
            height=380,
            key="generated_robin_script",
        )

        col_dl, col_lines = st.columns([2, 1])
        with col_dl:
            st.download_button(
                label="📥 Download Robin Script (.txt)",
                data=robin_script.encode("utf-8"),
                file_name="robin_script_llm.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with col_lines:
            line_count = len(robin_script.splitlines())
            st.caption(f"Total Actions / Lines: {line_count}")

        with st.expander("Formatted Syntax View"):
            st.code(robin_script, language="text")

    else:
        st.warning("No Robin script was generated.")
        st.info(
            "The model did not establish reliable Robin syntax for this bot. "
            "Review the action mapping below or provide verified PAD reference "
            "examples in the configuration section above."
        )

    if validation:
        with st.expander("Robin Validation Details"):
            st.write(
                validation.get(
                    "message",
                    "Validated and prepared for Power Automate Desktop canvas.",
                )
            )


def display_conversion_report(report):
    st.subheader("📊 Conversion Report")
    report = report or {}

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Activities", report.get("total_activities", 0))
    col2.metric("Converted", report.get("converted_activities", 0))
    col3.metric("Partial", report.get("partial_activities", 0))
    col4.metric("Unsupported", report.get("unsupported_activities", 0))

    warnings = report.get("warnings", [])
    if warnings:
        st.warning("Conversion Warnings")
        for warning in warnings:
            st.write(f"- {warning}")


def display_unsupported_activities(items):
    st.subheader("⚠️ Unsupported Activities")
    if not items:
        st.success("No unsupported activities were reported.")
        return

    st.warning(f"{len(items)} unsupported activities reported.")
    st.json(items)


def display_assumptions(items):
    st.subheader("📝 Assumptions & Notes")
    if not items:
        st.write("No assumptions reported.")
        return

    for item in items:
        st.write(f"- {item}")


# ============================================================
# LLM CONFIGURATION
# ============================================================

st.subheader("🔑 LLM Configuration")

col_ep, col_model, col_key = st.columns([2.2, 1.3, 1.5])

with col_ep:
    endpoint = st.text_input(
        "Endpoint",
        key="llm_endpoint",
        placeholder=DEFAULT_ENDPOINT,
    )

with col_model:
    model = st.text_input(
        "Model",
        key="llm_model",
        placeholder=DEFAULT_MODEL,
    )

with col_key:
    api_key = st.text_input(
        "API Key",
        type="password",
        key="llm_api_key",
        placeholder="Enter API Key (optional for localhost)",
    )


# ============================================================
# SIDEBAR SETTINGS
# ============================================================

with st.sidebar:
    st.header("⚙️ Settings")

    st.selectbox(
        "Provider Preset",
        list(PROVIDER_OPTIONS.keys()),
        key="llm_preset",
        on_change=apply_provider_preset,
    )

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.1,
        step=0.05,
        help="Lower values (0.0 - 0.2) yield strict, deterministic code.",
    )

    st.divider()

    include_node_metadata = st.checkbox(
        "Include # node_id metadata lines",
        value=False,
        help="Prefix each Robin action with # node_id metadata lines.",
    )

    st.divider()

    has_key_or_local = (
        bool(api_key.strip())
        or (bool(endpoint.strip()) and is_local_endpoint(endpoint))
    )

    if endpoint.strip() and model.strip() and has_key_or_local:
        st.success(
            f"✅ Configured\n\n"
            f"**Endpoint:** `{endpoint.strip()}`\n\n"
            f"**Model:** `{model.strip()}`"
        )
    else:
        st.warning("Configure endpoint, model and API key to run LLM.")


# ============================================================
# VERIFIED ROBIN REFERENCE EXAMPLES
# ============================================================

st.subheader("📚 PAD Robin Reference Configuration")

st.info(
    "Pre-loaded with verified Power Automate Desktop Robin action syntax "
    "(Excel, File, Web, REST API, JSON, DataTables, Dialogs, Conditions, Loops). "
    "These references guide the LLM to generate genuine, pasteable PAD actions."
)

with st.expander(
    "View / Edit Verified PAD Robin Examples",
    expanded=False,
):
    col_ref_head, col_ref_reset = st.columns([4, 1])
    with col_ref_reset:
        if st.button("Reset to Default References", use_container_width=True):
            st.session_state["reference_examples"] = DEFAULT_ROBIN_REFERENCES
            st.rerun()

    reference_examples = st.text_area(
        "Verified PAD Robin syntax references",
        value=st.session_state.get("reference_examples", DEFAULT_ROBIN_REFERENCES),
        height=260,
        key="reference_examples",
    )

    if reference_examples.strip():
        st.success("✅ Robin reference examples active.")
    else:
        st.warning("⚠️ No reference examples provided. LLM may withhold Robin syntax.")


# ============================================================
# PROJECT UPLOAD
# ============================================================

st.divider()

st.subheader("📦 UiPath Project Upload")

uploaded = st.file_uploader(
    "Upload UiPath Project (.zip, .nupkg, or .xaml)",
    type=["zip", "nupkg", "xaml"],
)


# ============================================================
# PROJECT PROCESSING
# ============================================================

if uploaded is not None:
    st.write(f"**File:** `{uploaded.name}` | **Size:** `{uploaded.size:,}` bytes")

    extension = Path(uploaded.name).suffix.lower()
    raw_bytes = uploaded.getvalue()

    try:
        # Extract and analyze for LLM context
        if extension in [".zip", ".nupkg"]:
            with st.spinner("Extracting project files..."):
                project_folder = extract_zip(uploaded)
                xaml_files = get_xaml_files(project_folder)
                dlls = get_dll_files(project_folder)
                important_files = get_important_files(project_folder)
                project_tree = get_project_tree(project_folder)
                xml_context = build_xml_context(project_folder)
        else:
            xaml_files = [uploaded.name]
            dlls = []
            important_files = [uploaded.name]
            project_tree = f"└── {uploaded.name}"
            xml_context = (
                f"{'='*80}\nWORKFLOW XAML FILE: {uploaded.name}\n{'='*80}\n"
                + raw_bytes.decode("utf-8", errors="ignore")
            )

        # ----------------------------------------------------
        # PROJECT STATISTICS
        # ----------------------------------------------------
        st.subheader("📊 Project Statistics")
        col1, col2, col3 = st.columns(3)
        col1.metric("XAML Workflows", len(xaml_files))
        col2.metric("DLL Dependencies", len(dlls))
        col3.metric("Key Files", len(important_files))

        with st.expander("📁 Project Structure and Workflows"):
            st.code(project_tree, language="text")
            st.write("**Detected Workflows:**")
            for xaml_file in xaml_files:
                st.write(f"- {Path(xaml_file).name}")

        # ----------------------------------------------------
        # GENERATE MIGRATION
        # ----------------------------------------------------
        if st.button(
            "🚀 Generate PAD Migration",
            type="primary",
            use_container_width=True,
        ):
            if not endpoint.strip():
                st.error("Please enter an endpoint URL.")
                st.stop()

            if not model.strip():
                st.error("Please enter a model name.")
                st.stop()

            if not api_key.strip() and not is_local_endpoint(endpoint):
                st.error("Please enter your API key.")
                st.stop()

            if not xml_context.strip():
                st.error("The generated XAML context is empty.")
                st.stop()

            st.caption(
                f"Loaded {len(xml_context):,} characters of XAML context."
            )

            # Execute LLM
            with st.spinner(f"Analyzing UiPath workflow using {model}..."):
                result = execute_pure_llm(
                    api_key=api_key.strip(),
                    model=model.strip(),
                    xml_context=xml_context,
                    dlls=dlls,
                    include_node_metadata=include_node_metadata,
                    temperature=temperature,
                    endpoint=endpoint.strip(),
                    reference_examples=reference_examples,
                )

            if not result.get("success"):
                st.error(
                    f"LLM Conversion Failed:\n\n{result.get('error', 'Unknown error')}"
                )
                st.stop()

            st.success("✅ LLM workflow analysis completed.")

            # Summary
            st.subheader("🧠 Workflow Understanding")
            st.write(result.get("summary", "No workflow summary returned."))

            # Action Mapping
            display_action_mapping(result.get("pad_action_mapping", []))

            # Generated Robin Script (Sanitized & Pasteable)
            display_robin_script(result)

            # Conversion Report
            display_conversion_report(result.get("conversion_report", {}))

            # Unsupported Activities
            display_unsupported_activities(result.get("unsupported_activities", []))

            # Assumptions
            display_assumptions(result.get("assumptions", []))

            # Export
            st.divider()
            st.subheader("📥 Export Migration Results")
            st.download_button(
                label="Download Complete Migration JSON",
                data=json.dumps(
                    result,
                    indent=4,
                    ensure_ascii=False,
                    default=str,
                ),
                file_name="migration_result.json",
                mime="application/json",
                use_container_width=True,
            )

    except Exception as ex:
        st.error(f"Error processing project: {str(ex)}")
