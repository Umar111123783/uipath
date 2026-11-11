import os
from pathlib import Path
from typing import List, Dict, Any
import streamlit as st

from llm import convert_to_robin
from parser import (
    extract_zip,
    build_xml_context,
    get_dll_files,
    get_xaml_files,
    get_important_files,
    get_project_tree,
)

# ==================================================
# Streamlit Page Config
# ==================================================
st.set_page_config(
    page_title="UiPath → PAD Robin (Pure LLM)",
    page_icon="🧠",
    layout="wide",
)

st.title("🧠 UiPath XAML → PAD Robin Converter (Pure LLM Engine)")
st.caption(
    "Direct AI-powered RPA migration using Google Gemini and OpenAI models. No local Python AST conversion."
)


def execute_pure_llm(
    api_key: str,
    model: str,
    xml_context: str,
    dlls: List[str],
    include_node_metadata: bool = False,
    temperature: float = 0.1,
) -> Dict[str, Any]:
    """Execute conversion strictly through the LLM module with no local Python AST fallback."""
    return convert_to_robin(
        api_key=api_key,
        model=model,
        xml_context=xml_context,
        dlls=dlls,
        temperature=temperature,
        include_node_metadata=include_node_metadata,
    )


# ==================================================
# Sidebar Controls
# ==================================================
with st.sidebar:
    st.header("🔑 LLM Settings")

    api_key = st.text_input(
        "API Key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", "") or os.environ.get("OPENAI_API_KEY", ""),
        placeholder="Paste your Gemini or OpenAI API Key...",
        help="Enter your Google Gemini API Key or OpenAI API Key.",
    )

    model = st.selectbox(
        "Select Model",
        [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-3.8-flash",
            "openai.gpt-4o-mini",
            "openai.gpt-4o",
        ],
        index=0,
        help="Select which AI model will generate the Robin script.",
    )

    temperature = st.slider(
        "Temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.1,
        step=0.05,
        help="Lower values (0.0 - 0.2) give deterministic, precise code output.",
    )

    st.markdown("---")
    st.subheader("⚙️ Output Format")
    include_node_metadata = st.checkbox(
        "Include # node_id metadata lines",
        value=True,
        help="Prefix each Robin action with `# node_id=<Bot>.<index>.<hex>; package=...; action=...; resolved=...` separated by blank lines.",
    )
    st.markdown("---")

    if api_key:
        st.success(f"✅ Key Configured! Target: **{model}**")
    else:
        st.warning("⚠️ Enter your API Key to enable pure LLM conversion.")

# ==================================================
# Upload & Conversion
# ==================================================
uploaded = st.file_uploader(
    "Upload UiPath Project (.zip or .nupkg)",
    type=["zip", "nupkg"],
)

if uploaded is not None:
    st.write(f"📄 **File:** `{uploaded.name}` | 📦 **Type:** `{uploaded.type}`")

    try:
        with st.spinner("Extracting project files..."):
            project_folder = extract_zip(uploaded)
            xaml_files = get_xaml_files(project_folder)
            dlls = get_dll_files(project_folder)
            important_files = get_important_files(project_folder)
            project_tree = get_project_tree(project_folder)

        col1, col2, col3 = st.columns(3)
        col1.metric("XAML Workflows", len(xaml_files))
        col2.metric("DLL Dependencies", len(dlls))
        col3.metric("Key Files", len(important_files))

        with st.expander("📁 Project Structure & Workflows"):
            st.code(project_tree, language="text")
            st.write("**Detected Workflows:**")
            for x in xaml_files:
                st.write(f"- `{Path(x).name}`")

        # ==================================================
        # Generate Button
        # ==================================================
        if st.button("🚀 Generate with LLM (Pure AI)", type="primary", use_container_width=True):
            if not api_key:
                st.error("🔑 Please enter your API Key in the sidebar before generating.")
                st.stop()

            with st.spinner("Building project context for LLM..."):
                xml_context = build_xml_context(project_folder)
                st.caption(f"Loaded {len(xml_context):,} characters of XAML context.")

            with st.spinner(f"Generating Robin Script using {model}... (Pure LLM)"):
                result = execute_pure_llm(
                    api_key=api_key,
                    model=model,
                    xml_context=xml_context,
                    dlls=dlls,
                    include_node_metadata=include_node_metadata,
                    temperature=temperature,
                )

            if not result.get("success"):
                st.error(f"❌ **LLM Conversion Failed:**\n\n{result.get('error')}")
                st.info(
                    "💡 Pure LLM mode does not perform local Python fallback. Check your API key, model selection, or server status."
                )
                if result.get("raw_response"):
                    with st.expander("🔍 Raw Server Response"):
                        st.code(result.get("raw_response"), language="json")
                st.stop()

            used_m = result.get("model_used", model)
            st.success(f"🤖 **Generated Exclusively by AI Model (`{used_m}`)**")

            st.subheader("📋 Business Summary")
            st.write(result.get("summary", "No summary generated."))

            st.subheader("⚡ Generated Power Automate Desktop (Robin) Script")
            st.info(
                "💡 **How to Copy Without HTML Corruption (`<br>`, `&gt;`, `<a href>`):**\n"
                "1. Click inside the **Plain Text** box below and press **Ctrl + A → Ctrl + C**, or click **Download Robin Script (.txt)**.\n"
                "2. Open your desktop flow in Power Automate Desktop.\n"
                "3. Click on the central canvas and press **Ctrl + V**."
            )

            robin_code = result.get("robin_script", "")
            st.text_area(
                "Plain Text Robin Script (Copy-Safe: Ctrl+A → Ctrl+C — never adds <br> or &gt;)",
                value=robin_code,
                height=320,
            )

            st.download_button(
                label="📥 Download Robin Script (.txt)",
                data=robin_code.encode("utf-8"),
                file_name="robin_script_llm.txt",
                mime="text/plain",
                use_container_width=True,
            )

            with st.expander("Formatted Code View (Use Plain Text Box Above to Copy)"):
                st.code(robin_code, language="text")

            with st.expander("🔍 View Raw LLM Model Response"):
                st.text(result.get("raw_response", ""))

    except Exception as ex:
        st.error(f"Error processing project: {str(ex)}")
