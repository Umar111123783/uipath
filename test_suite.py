import ast
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import os
import llm
from converter.project_manager import ProjectManager
from converter.selector_parser import build_parsed_selector
from converter.activity_converter import convert_comment
from converter.models import ParsedActivity
from converter.expression_parser import (
    convert_uipath_expression_to_robin,
    convert_uipath_condition_to_robin,
    convert_uipath_condition_with_casts,
    parse_uipath_duration
)
from parser import sanitize_robin_script

class TestUiPathToRobinConverter(unittest.TestCase):

    def setUp(self):
        self.pm = ProjectManager()

    def test_expression_parser(self):
        # Durations
        self.assertEqual(parse_uipath_duration("00:00:05"), 5.0)
        self.assertEqual(parse_uipath_duration("00:01:30"), 90.0)
        self.assertEqual(parse_uipath_duration("5"), 5.0)

        # Variables & Literals
        self.assertEqual(convert_uipath_expression_to_robin("[myVar]"), "%myVar%")
        self.assertEqual(convert_uipath_expression_to_robin("[\"Hello World\"]"), "$'''Hello World'''")
        self.assertEqual(convert_uipath_expression_to_robin("Hello World"), "$'''Hello World'''")
        self.assertEqual(convert_uipath_expression_to_robin("https://www.google.com"), "$'''https://www.google.com'''")
        self.assertEqual(convert_uipath_expression_to_robin("[count + 1]"), "%count + 1%")
        self.assertEqual(convert_uipath_expression_to_robin("[\"User: \" + username]"), "$'''User: %username%'''")

        # Conditions
        self.assertEqual(convert_uipath_condition_to_robin("[x > 5 AndAlso y < 10]"), "x > 5 AND y < 10")
        self.assertEqual(convert_uipath_condition_to_robin("[isDone = True]"), "isDone = True")

    def test_selector_parser(self):
        raw = "<html app='chrome.exe' title='Google' /><webctrl tag='INPUT' name='q' id='searchbox' />"
        sel = build_parsed_selector(raw, index=1, hint="SearchInput")
        self.assertIn("appmask", sel.control_code)
        self.assertEqual(sel.app_name, "chrome.exe")
        self.assertIn("@name='q'", sel.xpath)
        self.assertIn("input", sel.css)

    def test_sample_web_bot(self):
        zip_path = "sample_bots/UiPath_Web_Search_Bot.zip"
        self.assertTrue(os.path.exists(zip_path))
        with open(zip_path, "rb") as f:
            proj = self.pm.process_zip_bytes(f.read())
        self.assertEqual(proj.name, "UiPath_Web_Search_Bot")
        self.assertGreater(proj.total_activities, 10)
        self.assertEqual(proj.total_unmapped, 0)
        robin = self.pm.get_full_project_robin(proj)
        self.assertIn("WebAutomation.LaunchChrome.LaunchChrome", robin)
        self.assertIn("WebAutomation.Click.Click", robin)
        self.assertIn("WebAutomation.FormFilling.PopulateTextField.Populate", robin)
        self.assertIn("FUNCTION Main", robin)
        self.assertIn("FUNCTION LogResults", robin)

    def test_sample_excel_bot(self):
        zip_path = "sample_bots/UiPath_Excel_Processor_Bot.zip"
        with open(zip_path, "rb") as f:
            proj = self.pm.process_zip_bytes(f.read())
        self.assertGreater(proj.total_activities, 5)
        self.assertEqual(proj.total_unmapped, 0)
        robin = self.pm.get_full_project_robin(proj)
        self.assertIn("Excel.LaunchExcel.LaunchAndOpenUnderExistingProcess", robin)
        self.assertIn("Excel.ReadFromExcel.ReadAllCells", robin)
        self.assertIn("LOOP FOREACH", robin)

    def test_sample_file_bot(self):
        zip_path = "sample_bots/UiPath_File_Automation_Bot.zip"
        with open(zip_path, "rb") as f:
            proj = self.pm.process_zip_bytes(f.read())
        self.assertGreater(proj.total_activities, 5)
        self.assertEqual(proj.total_unmapped, 0)
        robin = self.pm.get_full_project_robin(proj)
        self.assertIn("Folder.Create", robin)
        self.assertIn("File.WriteText.WriteText", robin)
        self.assertIn("System.RunApplication.RunApplicationAndWaitForExit", robin)
        self.assertIn("System.TerminateProcess.TerminateProcessByName", robin)

    def test_real_data_age_checker(self):
        pkg_path = "data/AgeChecker.1.0.1 4.nupkg"
        if os.path.exists(pkg_path):
            with open(pkg_path, "rb") as f:
                proj = self.pm.process_zip_bytes(f.read())
            self.assertEqual(proj.name, "AgeChecker")
            self.assertEqual(proj.total_unmapped, 0)
            robin = self.pm.get_clean_pasteable_robin(proj)
            lines = robin.splitlines()
            self.assertIn("SET userAgeText TO $''''''", lines)
            self.assertIn("Display.InputDialog", robin)
            self.assertIn("IF ButtonPressed = $'''OK''' THEN", lines)
            self.assertIn("    Text.ToNumber Text: userAgeText Number=> userAgeText_Num", lines)
            self.assertIn("    IF userAgeText_Num >= 18 THEN", lines)
            self.assertIn("    ELSE", lines)
            self.assertIn("        Display.ShowMessageDialog.ShowMessage", robin)
            self.assertNotIn("# POWER AUTOMATE DESKTOP", robin)
            self.assertNotIn("# node_id=", robin)
            self.assertNotIn("# --- Initialize Variables ---", robin)
            self.assertNotIn("# Project:", robin)
            self.assertNotIn("# Instructions:", robin)
            self.assertNotIn("# ****", robin)
            self.assertTrue(all(line != "" for line in lines))

    def test_real_data_crud_operation(self):
        pkg_path = "data/CrudOperation.1.0.1 2.nupkg"
        if os.path.exists(pkg_path):
            with open(pkg_path, "rb") as f:
                proj = self.pm.process_zip_bytes(f.read())
            self.assertEqual(proj.name, "CrudOperation")
            self.assertEqual(proj.total_unmapped, 0)
            robin = self.pm.get_full_project_robin(proj)
            self.assertIn("Web.InvokeWebService.InvokeWebService", robin)
            self.assertIn("Variables.ConvertJsonToCustomObject", robin)
            self.assertIn("Variables.CreateNewDatatable", robin)

            # 1. Variable initialization: No .NET constructors
            self.assertNotIn("%new JObject()%", robin)
            self.assertNotIn("%New JArray()%", robin)
            self.assertIn("Variables.ConvertJsonToCustomObject Json: $'''{}''' CustomObject=> jsonObj", robin)
            self.assertIn("Variables.CreateNewList List=> jsonArray", robin)

            # 2. Form input prompts for POST/PUT variables
            self.assertIn("UserInput=> newPostTitle", robin)
            self.assertIn("UserInput=> newPostDesc", robin)

            # 3. PUT method mapped correctly
            self.assertIn("Method: Web.Method.Put", robin)

            # 4. DELETE endpoint extracted from RequestUrl
            self.assertIn("Url: $'''https://jsonplaceholder.typicode.com/posts/%delPostId%''' Method: Web.Method.Delete", robin)

            # 5. HTTP response status verification wrapping success messages and stopping flow on error
            self.assertIn("IF responseStatus >= 200 AND responseStatus < 300 THEN", robin)
            self.assertIn("FlowControl.StopFlow", robin)

            # 6. DataTable row mapping uses CurrentItem and rowToAdd
            self.assertNotIn('currentJToken', robin)
            self.assertIn("Variables.AddRowToDataTable.AppendRowToDataTable DataTable: dtPosts RowToAdd:", robin)

            # 7. Excel workbook and sheet setup
            self.assertIn("IF (File.IfFile.Exists File: %excelPath%) THEN", robin)
            self.assertIn("Excel.SetActiveWorksheet.ActivateWorksheetByName", robin)
            self.assertIn("Excel.WriteToExcel.WriteCell", robin)
            self.assertIn("Excel.CloseExcel.CloseAndSaveAs", robin)

    def test_real_data_employee_onboarding(self):
        pkg_path = "data/EmployeeOnboardingBot.1.0.1 2.nupkg"
        if os.path.exists(pkg_path):
            with open(pkg_path, "rb") as f:
                proj = self.pm.process_zip_bytes(f.read())
            self.assertEqual(proj.name, "EmployeeOnboardingBot")
            self.assertEqual(proj.total_unmapped, 0)
            robin = self.pm.get_full_project_robin(proj)
            self.assertIn("Excel.LaunchExcel.LaunchAndOpenUnderExistingProcess", robin)
            self.assertIn("SWITCH %department%", robin)
            self.assertIn("CASE $'''IT'''", robin)

    def test_condition_casts_and_typed_variables(self):
        cond_cast, vars_cast = convert_uipath_condition_with_casts("[CInt(userAgeText) >= 18]")
        self.assertEqual(cond_cast, "userAgeText_Num >= 18")
        self.assertEqual(vars_cast, ["userAgeText"])

        cond_text, vars_text = convert_uipath_condition_with_casts("[userAgeText >= 18]", text_vars={"userAgeText"})
        self.assertEqual(cond_text, "userAgeText_Num >= 18")
        self.assertEqual(vars_text, ["userAgeText"])

        cond_int, vars_int = convert_uipath_condition_with_casts("[rowCount > 50]", text_vars={"userAgeText"})
        self.assertEqual(cond_int, "rowCount > 50")
        self.assertEqual(vars_int, [])

        xaml = """<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
          xmlns:ui="http://schemas.uipath.com/workflow/activities">
          <Sequence DisplayName="Main">
            <Sequence.Variables>
              <Variable x:TypeArguments="x:Int32" Name="rowCount" Default="0" />
            </Sequence.Variables>
            <If Condition="[rowCount &gt; 50]" DisplayName="Check Row Count">
              <If.Then>
                <ui:MessageBox Caption="Info" Text="Large batch" />
              </If.Then>
            </If>
          </Sequence>
        </Activity>"""
        proj = self.pm.process_single_xaml(xaml, filename="Main.xaml")
        robin = self.pm.get_clean_pasteable_robin(proj)
        self.assertIn("SET rowCount TO 0", robin)
        self.assertIn("IF rowCount > 50 THEN", robin)
        self.assertNotIn("Text.ToNumber", robin)

    def test_sanitize_robin_script_and_comment_filtering(self):
        dirty = "\n".join([
            "# ========================================================",
            "# POWER AUTOMATE DESKTOP (ROBIN SCRIPT)",
            "# Project: Main",
            "# Total Workflows: 1",
            "# Instructions: Copy all text below",
            "# [ControlRepositoryFolder]",
            "#   appmask > button",
            "# End ControlRepositoryFolder",
            "# node_id=Main 1.00001.5ff6cb8c; package=Comment; action=Comment; resolved=comment",
            "# ************************TASK NAME: Main ************************************",
            "# --- Initialize Variables ---",
            "",
            "SET userAgeText TO $''''''",
            "# Validate applicant eligibility",
            "IF userAgeText = $'''18''' THEN",
            "    WebAutomation.Click.Click BrowserInstance: Browser Control: appmask # XPath: //button",
            "",
            "END",
        ])
        cleaned = sanitize_robin_script(dirty)
        self.assertEqual(
            cleaned,
            "\n".join([
                "SET userAgeText TO $''''''",
                "# Validate applicant eligibility",
                "IF userAgeText = $'''18''' THEN",
                "    WebAutomation.Click.Click BrowserInstance: Browser Control: appmask",
                "END",
            ]),
        )

        real_comment = ParsedActivity(id="1", type_name="Comment", display_name="Comment", properties={"Text": "Check business rule"})
        self.assertEqual(convert_comment(real_comment), "# Check business rule")
        for deco in ["********************************", "---- Initialize Variables ----", "================", "Comment"]:
            deco_act = ParsedActivity(id="2", type_name="Comment", display_name="Comment", properties={"Text": deco})
            self.assertEqual(convert_comment(deco_act), "")

    def test_app_and_llm_separation(self):
        def collect_imports(filepath):
            with open(filepath, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=filepath)
            mods = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        mods.add(alias.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods.add(node.module.split(".")[0])
            return mods

        app_imports = collect_imports("app.py")
        self.assertNotIn("llm", app_imports)
        self.assertIn("converter", app_imports)

        llm_imports = collect_imports("llm.py")
        self.assertNotIn("converter", llm_imports)

        app_llm_imports = collect_imports("app_llm.py")
        self.assertNotIn("converter", app_llm_imports)
        self.assertIn("llm", app_llm_imports)

        res = llm.convert_to_robin("", "gemini-2.0-flash", "<Activity/>", [])
        self.assertFalse(res["success"])
        self.assertEqual(res["robin_script"], "")
        self.assertIn("API Key", res["error"])

    def test_llm_mock_clean_robin_response(self):
        fake_json = json.dumps({
            "summary": "Prompts user for age.",
            "robin_script": (
                "# POWER AUTOMATE DESKTOP (ROBIN SCRIPT)\n"
                "# node_id=Main 1.00001.abc; package=String; action=assign; resolved=assign\n"
                "SET userAgeText TO $''''''\n"
                "Display.InputDialog Title: $'''Age''' Message: $'''Enter age''' InputType: Display.InputType.SingleLine IsTopMost: False UserInput=> userAgeText ButtonPressed=> ButtonPressed"
            ),
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": fake_json}]}}]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("llm.requests.post", return_value=mock_resp) as post_mock, patch(
                "llm.Path", side_effect=lambda p: __import__("pathlib").Path(tmpdir) / p
            ):
                res = llm.convert_to_robin("test-key", "gemini-2.0-flash", "<Activity/>", [], temperature=0.0)

        self.assertTrue(post_mock.called)
        self.assertTrue(res["success"])
        self.assertEqual(res["engine"], "LLM")
        self.assertEqual(res["summary"], "Prompts user for age.")
        self.assertNotIn("# node_id=", res["robin_script"])
        self.assertNotIn("POWER AUTOMATE DESKTOP", res["robin_script"])
        self.assertIn("SET userAgeText TO $''''''", res["robin_script"])

if __name__ == "__main__":
    unittest.main()
