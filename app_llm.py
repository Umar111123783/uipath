
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
# CONFIGURATION
# ============================================================

DEFAULT_ENDPOINT = (
    "https://genai-sharedservice-apac.pwcinternal.com/chat/completions"
)

DEFAULT_MODEL = "openai.global.gpt-4.1"


# ============================================================
# STREAMLIT PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="UiPath to PAD Robin Migration",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 UiPath XAML → Power Automate Desktop Robin Converter")

st.caption(
    "AI-powered UiPath migration using PwC GenAI or another "
    "OpenAI-compatible LLM provider. "
    "Structured workflow analysis and reference-guided Robin generation."
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


def apply_provider_preset():

    preset = PROVIDER_OPTIONS.get(
        st.session_state.get("llm_preset", ""),
        {},
    )

    st.session_state["llm_endpoint"] = preset.get(
        "endpoint", ""
    )

    st.session_state["llm_model"] = preset.get(
        "model", ""
    )


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

    """
    Execute migration exclusively through llm.py.

    No local Python AST conversion or fallback.
    """

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

        st.warning(
            "No PAD action mapping was returned."
        )

        return

    display_rows = []

    for index, item in enumerate(mapping, start=1):

        display_rows.append({
            "No.": index,
            "Source Activity": item.get(
                "source_activity", ""
            ),
            "Source Type": item.get(
                "source_activity_type", ""
            ),
            "PAD Action": item.get(
                "pad_action", ""
            ),
            "Status": item.get(
                "conversion_status", ""
            ),
            "Description": item.get(
                "description", ""
            ),
            "Variables": ", ".join(
                item.get("variables", [])
                if isinstance(item.get("variables", []), list)
                else []
            ),
            "Notes": item.get(
                "notes", ""
            ),
        })

    st.dataframe(
        display_rows,
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("View Complete Action Mapping"):

        st.json(mapping)

    st.download_button(
        label="Download Action Mapping JSON",
        data=json.dumps(
            mapping,
            indent=4,
            ensure_ascii=False,
        ),
        file_name="pad_action_mapping.json",
        mime="application/json",
    )


def display_robin_script(result):

    st.subheader("⚡ Generated PAD Robin Script")

    robin_script = (
        result.get("robin_script") or ""
    ).strip()

    validation = result.get(
        "robin_script_validation",
        {},
    )

    if robin_script:

        status = validation.get(
            "status", "unverified"
        )

        if status == "reference_aligned_unverified":

            st.warning(
                "Basic checks passed and reference examples were "
                "provided. The script has NOT been verified by "
                "the PAD runtime. Test it before execution."
            )

        elif status == "verified":

            st.success(
                "Robin syntax verification status: verified."
            )

        else:

            st.info(
                "Generated script requires manual PAD validation."
            )

        st.text_area(
            "Plain Text Robin Script",
            value=robin_script,
            height=400,
            key="generated_robin_script",
        )

        st.download_button(
            label="📥 Download Robin Script (.txt)",
            data=robin_script.encode("utf-8"),
            file_name="robin_script_llm.txt",
            mime="text/plain",
            use_container_width=True,
        )

        with st.expander("Formatted Robin Code"):

            st.code(
                robin_script,
                language="text",
            )

    else:

        st.warning(
            "No Robin script was generated."
        )

        st.info(
            "The model did not establish reliable Robin syntax. "
            "The workflow analysis and PAD action mapping can still "
            "be used to construct the desktop flow."
        )

    if validation:

        st.write("**Robin Validation Details**")

        st.write(
            validation.get(
                "message",
                "No validation details available.",
            )
        )


def display_conversion_report(report):

    st.subheader("📊 Conversion Report")

    report = report or {}

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Activities",
        report.get("total_activities", 0),
    )

    col2.metric(
        "Converted",
        report.get("converted_activities", 0),
    )

    col3.metric(
        "Partial",
        report.get("partial_activities", 0),
    )

    col4.metric(
        "Unsupported",
        report.get("unsupported_activities", 0),
    )

    warnings = report.get("warnings", [])

    if warnings:

        st.warning("Conversion Warnings")

        for warning in warnings:

            st.write(f"- {warning}")


def display_unsupported_activities(items):

    st.subheader("⚠️ Unsupported Activities")

    if not items:

        st.success(
            "No unsupported activities were reported."
        )

        return

    st.warning(
        f"{len(items)} unsupported activities reported."
    )

    st.json(items)


def display_assumptions(items):

    st.subheader("📝 Assumptions")

    if not items:

        st.write("No assumptions reported.")

        return

    for item in items:

        st.write(f"- {item}")


# ============================================================
# LLM CONFIGURATION
# ============================================================

st.subheader("🔑 LLM Configuration")

col_ep, col_model, col_key = st.columns(
    [2.2, 1.3, 1.5]
)

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
        placeholder="Enter API Key",
    )


# ============================================================
# SIDEBAR SETTINGS
# ============================================================

with st.sidebar:

    st.header("⚙️ LLM Settings")

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
    )

    st.divider()

    include_node_metadata = st.checkbox(
        "Include Node ID Metadata",
        value=True,
        help=(
            "Request node ID and package metadata "
            "when supported by the supplied Robin references."
        ),
    )

    st.divider()

    has_key_or_local = (
        bool(api_key.strip())
        or (
            bool(endpoint.strip())
            and is_local_endpoint(endpoint)
        )
    )

    if endpoint.strip() and model.strip() and has_key_or_local:

        st.success(
            f"Configured\n\n"
            f"Model: {model.strip()}"
        )

    else:

        st.warning(
            "Configure endpoint, model and API key."
        )


# ============================================================
# VERIFIED ROBIN REFERENCE EXAMPLES
# ============================================================

st.subheader("📚 PAD Robin Reference Configuration")

st.info(
    "Provide actual Robin code exported from a working "
    "Power Automate Desktop flow. These references help "
    "the LLM reproduce your environment's syntax."
)

with st.expander(
    "Add Verified PAD Robin Examples",
    expanded=True,
):

    reference_examples = st.text_area(
        "Paste actual PAD Robin syntax",
        height=260,
        placeholder=(
            "Paste exported Robin examples here.\n\n"
            "Recommended examples:\n"
            "1. Input dialog\n"
            "2. Set variable / conversion\n"
            "3. IF / ELSE\n"
            "4. Display message\n"
            "5. Node metadata"
        ),
        key="reference_examples",
    )

    if reference_examples.strip():

        st.success(
            "Robin reference examples supplied."
        )

    else:

        st.warning(
            "No reference examples supplied. "
            "The updated LLM module will withhold unverified "
            "Robin script output."
        )


# ============================================================
# PROJECT UPLOAD
# ============================================================

st.divider()

st.subheader("📦 UiPath Project Upload")

uploaded = st.file_uploader(
    "Upload UiPath Project (.zip or .nupkg)",
    type=["zip", "nupkg"],
)


# ============================================================
# PROJECT PROCESSING
# ============================================================

if uploaded is not None:

    st.write(
        f"**File:** `{uploaded.name}`"
    )

    try:

        with st.spinner("Extracting project files..."):

            project_folder = extract_zip(uploaded)

            xaml_files = get_xaml_files(
                project_folder
            )

            dlls = get_dll_files(
                project_folder
            )

            important_files = get_important_files(
                project_folder
            )

            project_tree = get_project_tree(
                project_folder
            )

        # ----------------------------------------------------
        # PROJECT STATISTICS
        # ----------------------------------------------------

        st.subheader("📊 Project Statistics")

        col1, col2, col3 = st.columns(3)

        col1.metric(
            "XAML Workflows",
            len(xaml_files),
        )

        col2.metric(
            "DLL Dependencies",
            len(dlls),
        )

        col3.metric(
            "Important Files",
            len(important_files),
        )

        # ----------------------------------------------------
        # PROJECT STRUCTURE
        # ----------------------------------------------------

        with st.expander(
            "📁 Project Structure and Workflows"
        ):

            st.code(
                project_tree,
                language="text",
            )

            st.write("**Detected Workflows:**")

            for xaml_file in xaml_files:

                st.write(
                    f"- {Path(xaml_file).name}"
                )

        # ----------------------------------------------------
        # GENERATE MIGRATION
        # ----------------------------------------------------

        if st.button(
            "🚀 Generate PAD Migration",
            type="primary",
            use_container_width=True,
        ):

            # Validate endpoint

            if not endpoint.strip():

                st.error("Please enter an endpoint URL.")

                st.stop()

            # Validate model

            if not model.strip():

                st.error("Please enter a model name.")

                st.stop()

            # Validate API key

            if (
                not api_key.strip()
                and not is_local_endpoint(endpoint)
            ):

                st.error("Please enter your API key.")

                st.stop()

            # Validate XAML

            if not xaml_files:

                st.error(
                    "No XAML workflows found in the uploaded project."
                )

                st.stop()

            # ------------------------------------------------
            # BUILD XML CONTEXT
            # ------------------------------------------------

            with st.spinner(
                "Building UiPath workflow context..."
            ):

                xml_context = build_xml_context(
                    project_folder
                )

            if not xml_context.strip():

                st.error(
                    "The generated XAML context is empty."
                )

                st.stop()

            st.caption(
                f"Loaded {len(xml_context):,} characters "
                "of XAML context."
            )

            # ------------------------------------------------
            # EXECUTE LLM
            # ------------------------------------------------

            with st.spinner(
                f"Analyzing UiPath workflow using {model}..."
            ):

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

            # ------------------------------------------------
            # HANDLE FAILURE
            # ------------------------------------------------

            if not result.get("success"):

                st.error(
                    f"LLM Conversion Failed:\n\n"
                    f"{result.get('error', 'Unknown error')}"
                )

                raw_response = result.get(
                    "raw_response",
                    "",
                )

                if raw_response:

                    with st.expander("Raw Server Response"):

                        st.code(
                            raw_response,
                            language="text",
                        )

                st.stop()

            # ------------------------------------------------
            # SUCCESS
            # ------------------------------------------------

            st.success(
                "LLM workflow analysis completed."
            )

            st.caption(
                f"Model: {result.get('model_used', model)}"
            )

            st.caption(
                f"Endpoint: {result.get('endpoint_used', endpoint)}"
            )

            # ------------------------------------------------
            # WORKFLOW SUMMARY
            # ------------------------------------------------

            st.subheader("🧠 Workflow Understanding")

            st.write(
                result.get(
                    "summary",
                    "No workflow summary returned.",
                )
            )

            # ------------------------------------------------
            # ACTION MAPPING
            # ------------------------------------------------

            display_action_mapping(
                result.get(
                    "pad_action_mapping",
                    [],
                )
            )

            # ------------------------------------------------
            # ROBIN SCRIPT
            # ------------------------------------------------

            display_robin_script(result)

            # ------------------------------------------------
            # CONVERSION REPORT
            # ------------------------------------------------

            display_conversion_report(
                result.get(
                    "conversion_report",
                    {},
                )
            )

            # ------------------------------------------------
            # UNSUPPORTED ACTIVITIES
            # ------------------------------------------------

            display_unsupported_activities(
                result.get(
                    "unsupported_activities",
                    [],
                )
            )

            # ------------------------------------------------
            # ASSUMPTIONS
            # ------------------------------------------------

            display_assumptions(
                result.get(
                    "assumptions",
                    [],
                )
            )

            # ------------------------------------------------
            # RAW RESPONSE
            # ------------------------------------------------

            with st.expander(
                "🔍 Raw LLM API Response"
            ):

                st.text(
                    result.get(
                        "raw_response",
                        "",
                    )
                )

            # ------------------------------------------------
            # COMPLETE JSON DOWNLOAD
            # ------------------------------------------------

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

        st.error(
            f"Error processing project: {str(ex)}"
        )
