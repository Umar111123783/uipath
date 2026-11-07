# 🤖 UiPath to Power Automate (Robin) Converter - Streamlit App & Training Hub

A Streamlit web application and fine-tuning dataset hub that accepts UiPath bot `.zip` and `.nupkg` packages (or `.xaml` workflow files) and converts them into native **Microsoft Power Automate Desktop (Robin)** scripting language, ready to be pasted (`Ctrl+V`) directly into the Power Automate flow designer canvas.

---

## 🌟 Key Features

1. **Enterprise Dataset & `.nupkg` Archive Support**:
   - Supports both `.zip` bot projects and published UiPath NuGet package archives (`.nupkg` files) found in `data/`:
     - 🎓 **`AgeChecker`**: User `InputDialog`, type casting (`CInt`), conditional branches, and message dialogs.
     - 🎓 **`CrudOperation`**: Full REST API automation (`HttpClient`, GET/POST/PUT/DELETE, headers, body), JSON serialization/deserialization (`DeserializeJson`, `DeserializeJsonArray`), and data table builds (`BuildDataTable`, `AddDataRow`).
     - 🎓 **`EmployeeOnboardingBot`**: Modern Excel automation (`ExcelProcessScopeX`, `ExcelApplicationCard`, `ReadRangeX`, `WriteRangeX`), row loops (`ForEachRow`), conditional branches, directory creations (`CreateDirectory`), text output, and multi-branch `Switch` statements.
2. **Native Power Automate Desktop (Robin) Output**:
   - Converts UiPath activities into valid Robin script syntax.
   - Outputs both **Full Project** (with `FUNCTION Main ... END FUNCTION` for multi-subflow projects) and **Active Subflow** (pure action sequence for immediate canvas pasting).
3. **UI Selector & XPath/CSS Translation**:
   - Extracts UiPath XML selectors (`<webctrl>`, `<html app='chrome.exe'>`, `<wnd>`).
   - Translates them into **XPath** (`//input[@name='q']`) and **CSS Selectors** (`input[name="q"]`).
   - Generates `# [ControlRepositoryFolder]` definitions with `appmask[...]` controls.
4. **🎓 Model Training & Dataset Hub**:
   - Built-in dataset generator (`training/dataset_builder.py`) that extracts 70+ paired training examples (`UiPath Activity Properties -> PAD Robin Code`).
   - Export formats for model training:
     - `data/training_dataset_alpaca.json` (Instruction-tuning format)
     - `data/training_dataset_openai.jsonl` (Chat fine-tuning format for OpenAI, Gemini, Hugging Face, Llama)
     - `data/training_pairs.json` (Structured JSON)
   - Live benchmark runner achieving **100.0% conversion accuracy across all training packages**.
5. **Printable View & Clipboard Copy**:
   - 1-click **Copy to Clipboard**.
   - Download as `.robin` or `.txt`.
   - Formatted printable view for documentation and PDF export.

---

## 🚀 How to Run the Streamlit Application

```bash
streamlit run app.py
```

The application will launch in your browser at `http://localhost:8501`.

---

## 📋 How to Paste the Converted Code into Power Automate Desktop

1. **In the Streamlit App**:
   - Select your bot from the sidebar (or upload your own `.zip` / `.nupkg` / `.xaml`).
   - Go to the **📋 Power Automate Robin Script** tab.
   - Click the **Copy** icon at the top right of the code block.
2. **In Power Automate for desktop (PAD)**:
   - Create or open a flow in Power Automate Desktop.
   - Click anywhere on the empty flow designer canvas.
   - Press **`Ctrl + V`** on your keyboard (or right-click &rarr; **Paste**).
   - Power Automate will instantly parse the Robin text into visual action blocks!

---

## 🏗️ Architecture

```
uipath/
├── app.py                         # Streamlit application UI with Training Hub
├── test_suite.py                  # Unit tests covering sample & data packages
├── data/                          # Real enterprise training bot packages
│   ├── AgeChecker.1.0.1 4.nupkg
│   ├── CrudOperation.1.0.1 2.nupkg
│   ├── EmployeeOnboardingBot.1.0.1 2.nupkg
│   ├── training_dataset_alpaca.json    # Alpaca fine-tuning dataset
│   ├── training_dataset_openai.jsonl   # Chat fine-tuning dataset
│   └── training_pairs.json             # Structured activity pairs
├── training/
│   └── dataset_builder.py         # Training dataset extraction & benchmark engine
├── sample_bots/                   # Preloaded sample bots
│   ├── UiPath_Web_Search_Bot.zip
│   ├── UiPath_Excel_Processor_Bot.zip
│   └── UiPath_File_Automation_Bot.zip
└── converter/                     # Core conversion engine
    ├── __init__.py
    ├── models.py                  # Dataclasses
    ├── selector_parser.py         # UiPath selector to XPath/CSS & PAD control mapper
    ├── expression_parser.py       # Expression translation into Robin values
    ├── activity_converter.py      # UiPath activity to Robin action definitions
    ├── uipath_parser.py           # Recursive XAML XML parser
    └── project_manager.py         # Multi-flow & ZIP/NUPKG package orchestrator
```
