
import os
import re
import streamlit as st
from pathlib import Path
from typing import List, Dict, Any

from llm import (
    PROVIDER_PRESETS as ORIGINAL_PROVIDER_PRESETS,
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
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="UiPath → PAD Robin | PwC GenAI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧠 UiPath XAML → PAD Robin Converter")

st.caption(
    "Pure LLM-powered RPA migration engine | "
    "PwC GenAI GPT-4.1 | Gemini | OpenAI | Custom Endpoints"
)


# ============================================================
# APPLICATION CONFIGURATION
# ============================================================

PWC_ENDPOINT = (
    "https://genai-sharedservice-apac.pwcinternal.com/chat/completions"
)

PWC_MODEL = "openai.global.gpt-4.1"

MAX_UPLOAD_SIZE_MB = 500


# ============================================================
# PROVIDER PRESETS
# ============================================================

PROVIDER_PRESETS = dict(ORIGINAL_PROVIDER_PRESETS)

PROVIDER_PRESETS["PwC GenAI"] = {
    "endpoint": PWC_ENDPOINT,
    "model": PWC_MODEL,
}


# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================

DEFAULTS = {
    "llm_preset": "PwC GenAI",
    "llm_endpoint": os.getenv("LLM_ENDPOINT", PWC_ENDPOINT),
    "llm_model": os.getenv("LLM_MODEL", PWC_MODEL),
    "llm_api_key": (
        os.getenv("LLM_API_KEY", "")
        or os.getenv("PWC_API_KEY", "")
        or os.getenv("GEMINI_API_KEY", "")
        or os.getenv("OPENAI_API_KEY", "")
    ),
    "conversion_result": None,
    "uploaded_project_name": None,
    "robin_output": "",
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# PROVIDER PRESET CALLBACK
# ============================================================

def apply_provider_preset():

    selected = st.session_state.get(
        "llm_preset",
        "PwC GenAI",
    )

    preset = PROVIDER_PRESETS.get(selected, {})

    st.session_state["llm_endpoint"] = preset.get(
        "endpoint",
        "",
    )

    st.session_state["llm_model"] = preset.get(
        "model",
        "",
    )


# ============================================================
# AUTHENTICATION VALIDATION
# ============================================================

def validate_llm_configuration(
    endpoint: str,
    model: str,
    api_key: str,
) -> tuple[bool, str]:

    endpoint = endpoint.strip()
    model = model.strip()
    api_key = api_key.strip()

    if not endpoint:
        return False, "Please enter the LLM endpoint."

    if not model:
        return False, "Please enter the model name."

    if not api_key and not is_local_endpoint(endpoint):
        return False, "Please enter your API key."

    # PwC LiteLLM authentication validation
    normalized_endpoint = endpoint.rstrip("/").lower()
    normalized_pwc_endpoint = PWC_ENDPOINT.rstrip("/").lower()

    if normalized_endpoint == normalized_pwc_endpoint:

        if not api_key.startswith("sk-"):
            return (
                False,
                "Invalid PwC GenAI authentication key. "
                "Your endpoint requires a LiteLLM Virtual Key "
                "starting with 'sk-'. The supplied AQ.A credential "
                "is not accepted by this gateway. "
                "Please obtain the correct key from your PwC "
                "GenAI administrator.",
            )

    return True, ""


# ============================================================
# LLM ERROR HANDLING
# ============================================================

def format_llm_error(error: Any) -> str:

    message = str(error)

    # HTTP 401 - Authentication error
    if "401" in message or "auth_error" in message.lower():

        return (
            "PwC GenAI Authentication Failed (401).\n\n"
            "The gateway rejected the API key.\n\n"
            "Expected authentication: LiteLLM Virtual Key "
            "starting with sk-.\n\n"
            "Action: Obtain a valid LiteLLM Virtual Key from "
            "your PwC GenAI administrator. Do not use an "
            "AQ.A credential unless explicitly supported."
        )

    # HTTP 403 - Permission error
    if "403" in message:

        return (
            "Access Forbidden (403).\n\n"
            "Your API key may be valid, but it does not have "
            "permission to access this endpoint or model.\n\n"
            "Check your PwC GenAI access permissions."
        )

    # HTTP 404 - Endpoint or model error
    if "404" in message:

        return (
            "Endpoint or Model Not Found (404).\n\n"
            "Verify the API endpoint and model deployment name."
        )

    # HTTP 429 - Rate limit
    if "429" in message:

        return (
            "Rate Limit Exceeded (429).\n\n"
            "The LLM gateway is receiving too many requests.\n"
            "Wait and try again later."
        )

    # HTTP 500 / 502 / 503 / 504
    if any(code in message for code in ["500", "502", "503", "504"]):

        return (
            "LLM Gateway Server Error.\n\n"
            "The model service may be temporarily unavailable.\n"
            "Try again later or contact the gateway administrator."
        )

    return message


# ============================================================
# PURE LLM CONVERSION ENGINE
# ============================================================

def execute_pure_llm(
    api_key: str,
    model: str,
    xml_context: str,
    dlls: List[str],
    include_node_metadata: bool = True,
    temperature: float = 0.1,
    endpoint: str = "",
) -> Dict[str, Any]:

    """
    Execute migration exclusively through the configured LLM.

    No local AST conversion.
    No Python conversion fallback.
    """

    return convert_to_robin(
        api_key=api_key.strip(),
        model=model.strip(),
        xml_context=xml_context,
        dlls=dlls,
        temperature=temperature,
        include_node_metadata=include_node_metadata,
        endpoint=endpoint.strip(),
    )


# ============================================================
# LLM CONFIGURATION
# ============================================================

st.subheader("🔑 LLM Configuration")

col1, col2, col3 = st.columns([2.2, 1.3, 1.5])

with col1:

    endpoint = st.text_input(
        "LLM Endpoint",
        key="llm_endpoint",
        placeholder=PWC_ENDPOINT,
        help="Enter PwC GenAI or a custom OpenAI-compatible endpoint.",
    )

with col2:

    model = st.text_input(
        "Model Name",
        key="llm_model",
        placeholder=PWC_MODEL,
    )

with col3:

    api_key = st.text_input(
        "API Key",
        type="password",
        key="llm_api_key",
        placeholder="Enter your API key",
        help="For PwC GenAI, use the LiteLLM Virtual Key beginning with sk-.",
    )


# ============================================================
# SIDEBAR SETTINGS
# ============================================================

with st.sidebar:

    st.header("⚙️ LLM Settings")

    st.selectbox(
        "Provider Preset",
        options=list(PROVIDER_PRESETS.keys()),
        key="llm_preset",
        on_change=apply_provider_preset,
    )

    st.markdown("---")

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.1,
        step=0.05,
    )

    st.markdown("---")

    st.subheader("🧾 Output Settings")

    include_node_metadata = st.checkbox(
        "Include # node_id metadata",
        value=True,
        help=(
            "Include node_id, package, action and resolved "
            "metadata in Robin output."
        ),
    )

    st.markdown("---")

    st.subheader("🔌 Connection Status")

    config_valid, config_error = validate_llm_configuration(
        endpoint,
        model,
        api_key,
    )

    if config_valid:

        st.success("LLM configuration completed")

        st.caption(f"Model: {model}")

        if endpoint.rstrip("/").lower() == PWC_ENDPOINT.rstrip("/").lower():
            st.caption("Authentication: LiteLLM Virtual Key")
        else:
            st.caption("Custom provider authentication")

    else:

        st.warning("LLM configuration incomplete")

        if endpoint.rstrip("/").lower() == PWC_ENDPOINT.rstrip("/").lower():
            st.error(
                "PwC requires a LiteLLM Virtual Key starting with sk-."
            )


# ============================================================
# PROJECT UPLOAD
# ============================================================

st.markdown("---")

st.subheader("📦 Upload UiPath Project")

uploaded = st.file_uploader(
    "Upload UiPath Project (.zip or .nupkg)",
    type=["zip", "nupkg"],
    help="Upload your UiPath project archive.",
)


if uploaded is not None:

    st.write(f"📄 **File:** `{uploaded.name}`")

    st.write(
        f"📦 **Size:** {uploaded.size / (1024 * 1024):.2f} MB"
    )

    if uploaded.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:

        st.error(
            f"File exceeds the {MAX_UPLOAD_SIZE_MB} MB upload limit."
        )

        st.stop()

    # ========================================================
    # PROJECT EXTRACTION
    # ========================================================

    try:

        with st.spinner("Extracting UiPath project..."):

            project_folder = extract_zip(uploaded)

            xaml_files = get_xaml_files(project_folder)

            dlls = get_dll_files(project_folder)

            important_files = get_important_files(project_folder)

            project_tree = get_project_tree(project_folder)

        st.success("Project extracted successfully!")

        # ====================================================
        # PROJECT METRICS
        # ====================================================

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
            "Key Files",
            len(important_files),
        )

        # ====================================================
        # PROJECT STRUCTURE
        # ====================================================

        with st.expander("📁 Project Structure & Workflows"):

            st.subheader("Project Tree")

            st.code(
                project_tree,
                language="text",
            )

            st.subheader("Detected XAML Workflows")

            if xaml_files:

                for xaml in xaml_files:
                    st.write(f"📄 `{Path(xaml).name}`")

            else:

                st.warning("No XAML workflow files detected.")

            st.subheader("DLL Dependencies")

            if dlls:

                for dll in dlls:
                    st.write(f"🔗 `{dll}`")

            else:

                st.info("No DLL dependencies detected.")

        # ====================================================
        # CONVERSION BUTTON
        # ====================================================

        st.markdown("---")

        if st.button(
            "🚀 Generate Robin Script with PwC GenAI",
            type="primary",
            use_container_width=True,
        ):

            # -----------------------------------------------
            # Validate configuration
            # -----------------------------------------------

            valid, validation_error = validate_llm_configuration(
                endpoint,
                model,
                api_key,
            )

            if not valid:

                st.error(validation_error)

                st.stop()

            if not xaml_files:

                st.error(
                    "No XAML workflows found. "
                    "Cannot perform UiPath migration."
                )

                st.stop()

            # -----------------------------------------------
            # Build XML context
            # -----------------------------------------------

            with st.spinner(
                "Building complete UiPath XML context..."
            ):

                xml_context = build_xml_context(
                    project_folder
                )

            if not xml_context or not xml_context.strip():

                st.error(
                    "Unable to build XML context from the project."
                )

                st.stop()

            st.info(
                f"📄 XML Context: {len(xml_context):,} characters"
            )

            # -----------------------------------------------
            # Execute LLM conversion
            # -----------------------------------------------

            try:

                with st.spinner(
                    f"🤖 Converting using {model}..."
                ):

                    result = execute_pure_llm(
                        api_key=api_key,
                        model=model,
                        xml_context=xml_context,
                        dlls=dlls,
                        include_node_metadata=include_node_metadata,
                        temperature=temperature,
                        endpoint=endpoint,
                    )

            except Exception as llm_error:

                st.error(
                    "❌ LLM Request Failed"
                )

                st.code(
                    format_llm_error(llm_error),
                    language="text",
                )

                with st.expander("Technical Error Details"):

                    st.code(
                        str(llm_error),
                        language="text",
                    )

                st.info(
                    "No local conversion fallback was executed."
                )

                st.stop()

            # -----------------------------------------------
            # Handle failed conversion
            # -----------------------------------------------

            if not result or not result.get("success"):

                st.error("❌ LLM Conversion Failed")

                error_message = (
                    result.get("error", "Unknown LLM error")
                    if result
                    else "Empty response from LLM."
                )

                st.code(
                    format_llm_error(error_message),
                    language="text",
                )

                if result and result.get("raw_response"):

                    with st.expander("🔍 Raw Server Response"):

                        st.code(
                            str(result["raw_response"]),
                            language="text",
                        )

                st.stop()

            # -----------------------------------------------
            # Store successful conversion
            # -----------------------------------------------

            st.session_state["conversion_result"] = result

            st.session_state["uploaded_project_name"] = uploaded.name

            st.session_state["robin_output"] = result.get(
                "robin_script",
                "",
            )

            st.success(
                "✅ UiPath to Robin conversion completed successfully!"
            )

        # ====================================================
        # DISPLAY CONVERSION RESULT
        # ====================================================

        result = st.session_state.get("conversion_result")

        if (
            result
            and st.session_state.get("uploaded_project_name")
            == uploaded.name
        ):

            used_model = result.get(
                "model_used",
                model,
            )

            used_endpoint = result.get(
                "endpoint_used",
                endpoint,
            )

            st.markdown("---")

            st.success(
                f"🤖 Generated exclusively by AI model: `{used_model}`"
            )

            st.caption(f"Endpoint: {used_endpoint}")

            robin_code = result.get(
                "robin_script",
                "",
            )

            if not robin_code:

                st.warning(
                    "LLM returned an empty Robin script."
                )

            else:

                st.subheader(
                    "⚡ Generated Power Automate Desktop Robin Script"
                )

                st.info(
                    """
                    **Copy Instructions**

                    1. Click inside the Plain Text box.
                    2. Press Ctrl + A.
                    3. Press Ctrl + C.
                    4. Open Power Automate Desktop.
                    5. Paste your Robin script using Ctrl + V.

                    Alternatively, download the TXT file below.
                    """
                )

                # -------------------------------------------
                # Plain text output
                # -------------------------------------------

                st.text_area(
                    "Plain Text Robin Script (Copy-Safe)",
                    value=robin_code,
                    height=450,
                    key="robin_output",
                )

                # -------------------------------------------
                # Download output
                # -------------------------------------------

                st.download_button(
                    label="📥 Download Robin Script (.txt)",
                    data=robin_code.encode("utf-8"),
                    file_name="robin_script_pwc_gpt41.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

                # -------------------------------------------
                # Formatted output
                # -------------------------------------------

                with st.expander("📝 Formatted Robin Code"):

                    st.code(
                        robin_code,
                        language="text",
                    )

                # -------------------------------------------
                # Raw LLM response
                # -------------------------------------------

                with st.expander("🔍 Raw LLM Model Response"):

                    st.text(
                        result.get("raw_response", "")
                    )

    except Exception as ex:

        st.error(
            f"❌ Error processing project: {str(ex)}"
        )

else:

    st.info(
        "👆 Upload a UiPath ZIP or NUPKG project to begin migration."
    )


# ============================================================
# FOOTER
# ============================================================

st.markdown("---")

st.caption(
    "UiPath → Power Automate Desktop | "
    "Pure LLM Migration Engine | PwC GenAI GPT-4.1"
)
