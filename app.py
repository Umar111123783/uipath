import os
import json
from pathlib import Path
import streamlit as st

from parser import (
    extract_zip,
    build_xml_context,
    get_dll_files,
    get_xaml_files,
    get_important_files,
    get_project_tree
)

from llm import convert_to_robin

st.set_page_config(
    page_title="UiPath Converter",
    page_icon="🤖",
    layout="wide"
)

st.title(
    "UiPath XAML → PAD Robin Converter"
)

# ==================================================
# Sidebar
# ==================================================

with st.sidebar:
    st.header("🔑 LLM Settings")

    api_key = st.text_input(
        "API Key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
        placeholder="Paste your Gemini or OpenAI API Key...",
        help="Enter your Google Gemini API Key or OpenAI API Key."
    )

    model = st.selectbox(
        "Select Model",
        [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-pro",
            "gemini-2.0-flash",
            "openai.gpt-4o-mini",
            "openai.gpt-4o"
        ],
        index=0,
        help="Select which AI model will generate the Robin script."
    )

    if api_key:
        st.success(f"✅ Key Configured! Model: **{model}**")
    else:
        st.warning("⚠️ Enter API Key to generate Robin script.")

# ==================================================
# Upload
# ==================================================

uploaded = st.file_uploader(
    "Upload UiPath Project (.zip or .nupkg)"
)

if uploaded is not None:

    st.write(
        f"📄 File Name: {uploaded.name}"
    )

    st.write(
        f"📦 Content Type: {uploaded.type}"
    )

    extension = Path(
        uploaded.name
    ).suffix.lower()

    if extension not in [
        ".zip",
        ".nupkg"
    ]:
        st.error(
            "Only .zip and .nupkg files are supported."
        )
        st.stop()

    try:

        # ==================================================
        # Extract
        # ==================================================

        project_folder = extract_zip(
            uploaded
        )

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

        if not xaml_files:
            st.warning(
                "No XAML files found inside package."
            )
            st.stop()

        # ==================================================
        # Statistics
        # ==================================================

        st.subheader(
            "Project Overview"
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "XAML Files",
                len(xaml_files)
            )

        with col2:
            st.metric(
                "DLL Files",
                len(dlls)
            )

        with col3:
            st.metric(
                "Important Files",
                len(important_files)
            )

        with st.expander(
            "Project Statistics"
        ):
            st.write(
                f"Project Folder: {project_folder}"
            )
            st.write(
                f"Total XAML Files: {len(xaml_files)}"
            )
            st.write(
                f"Total DLL Files: {len(dlls)}"
            )
            st.write(
                f"Important Files: {len(important_files)}"
            )

        # ==================================================
        # Project Tree
        # ==================================================

        with st.expander(
            "Project Tree Structure"
        ):
            st.code(
                project_tree,
                language="text"
            )

        # ==================================================
        # Important Files
        # ==================================================

        with st.expander(
            "Important Files Detected"
        ):
            for file in important_files:
                st.write(file)

        # ==================================================
        # XAML
        # ==================================================

        with st.expander(
            "Detected XAML Files"
        ):
            for file in xaml_files:
                st.write(
                    Path(file).name
                )

        # ==================================================
        # DLL
        # ==================================================

        with st.expander(
            "Detected DLL Files"
        ):
            if dlls:
                for dll in dlls:
                    st.write(
                        dll
                    )
            else:
                st.info(
                    "No DLL files found."
                )

        # ==================================================
        # Generate
        # ==================================================

        if st.button(
            "Generate Robin Script",
            type="primary",
            use_container_width=True
        ):

            if not api_key:
                st.error("🔑 Please enter your API Key in the left sidebar under 'LLM Settings' before generating.")
                st.stop()

            with st.spinner(
                "Reading project files..."
            ):
                xml_context = build_xml_context(
                    project_folder
                )

                with open(
                    "full_context.txt",
                    "w",
                    encoding="utf-8"
                ) as f:
                    f.write(
                        xml_context
                    )

                st.success(
                    f"Loaded {len(xml_context):,} characters from project."
                )

            # ==================================================
            # Preview Context
            # ==================================================

            with st.expander(
                "Preview Extracted Project Content"
            ):
                st.text(
                    xml_context[:5000]
                )

            # ==================================================
            # LLM
            # ==================================================

            with st.spinner(
                f"Generating Robin Script with {model}..."
            ):
                result = convert_to_robin(
                    api_key,
                    model,
                    xml_context,
                    dlls
                )

            # ==================================================
            # Summary
            # ==================================================

            st.subheader(
                "Business Summary"
            )

            st.write(
                result.get(
                    "summary",
                    "No summary generated."
                )
            )

            # ==================================================
            # Robin Script
            # ==================================================

            robin_script = result.get(
                "robin_script",
                ""
            )

            if isinstance(
                robin_script,
                (list, dict)
            ):
                robin_script = json.dumps(
                    robin_script,
                    indent=2,
                    ensure_ascii=False
                )

            robin_script = str(
                robin_script
            )

            st.subheader(
                "Generated Robin Script"
            )

            st.code(
                robin_script,
                language="text"
            )

            st.download_button(
                label="Download Robin Script",
                data=robin_script.encode(
                    "utf-8"
                ),
                file_name="robin_script.txt",
                mime="text/plain"
            )

        # ==================================================
        # Raw Response
        # ==================================================

        if Path(
            "model_response.txt"
        ).exists():
            with st.expander(
                "Raw Model Response"
            ):
                st.text(
                    Path(
                        "model_response.txt"
                    ).read_text(
                        encoding="utf-8"
                    )[:10000]
                )

    except Exception as ex:
        st.error(
            f"Error: {str(ex)}"
        )
