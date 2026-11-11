import ast
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import glob
import os
import re
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
from parser import apply_robin_node_metadata, sanitize_robin_script

class TestUiPathToRobinConverter(unittest.TestCase):

    def setUp(self):
        self.pm = ProjectManager()

    def test_expression_parser(self):
        # Durations
        self.assertEqual(parse_uipath_duration("00:00:05"), 5.0)
        self.assertEqual(parse_uipath_duration("00:01:30"), 90.0)
        self.assertEqual(parse_uipath_duration("5"), 5.0)

        # Variables & Literals
        self.assertEqual(convert_uipath_expression_to_robin("[myVar]"), "myVar")
        self.assertEqual(convert_uipath_expression_to_robin("[\"Hello World\"]"), "$'''Hello World'''")
        self.assertEqual(convert_uipath_expression_to_robin("Hello World"), "$'''Hello World'''")
        self.assertEqual(convert_uipath_expression_to_robin("https://www.google.com"), "$'''https://www.google.com'''")
        self.assertEqual(convert_uipath_expression_to_robin("[count + 1]"), "count + 1")
        self.assertEqual(convert_uipath_expression_to_robin('[jsonObj("title").ToString]'), "jsonObj['title']")
        self.assertEqual(convert_uipath_expression_to_robin("[New System.Data.DataTable()]"), "$''''''")
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
        self.assertIn("CALL LogResults", robin)
        self.assertNotIn("Flow.RunFlow", robin)

    def test_sample_excel_bot(self):
        zip_path = "sample_bots/UiPath_Excel_Processor_Bot.zip"
        with open(zip_path, "rb") as f:
            proj = self.pm.process_zip_bytes(f.read())
        self.assertGreater(proj.total_activities, 5)
        self.assertEqual(proj.total_unmapped, 0)
        robin = self.pm.get_full_project_robin(proj)
        self.assertIn("Excel.LaunchExcel.LaunchAndOpen Path: excelFilePath", robin)
        self.assertIn("Excel.LaunchExcel.Launch Visible: True LoadAddInsAndMacros: False Instance=> ExcelInstance", robin)
        self.assertIn("Excel.ReadFromExcel.ReadAllCells Instance: ExcelInstance ReadAsText: False FirstLineIsHeader: True RangeValue=> customersTable", robin)
        self.assertIn("LOOP FOREACH", robin)

    def test_sample_file_bot(self):
        zip_path = "sample_bots/UiPath_File_Automation_Bot.zip"
        with open(zip_path, "rb") as f:
            proj = self.pm.process_zip_bytes(f.read())
        self.assertGreater(proj.total_activities, 5)
        self.assertEqual(proj.total_unmapped, 0)
        robin = self.pm.get_full_project_robin(proj)
        self.assertIn("Folder.Create FolderPath: backupFolder", robin)
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
            self.assertIn("EXIT Code: 0", robin)
            self.assertNotIn("FlowControl.StopFlow", robin)
            self.assertIn("Variables.ConvertJsonToCustomObject Json: responseString CustomObject=> jsonArray", robin)
            self.assertIn("SET count TO jsonArray.Count", robin)
            self.assertIn("RequestBody: requestBody", robin)

            # 6. DataTable row mapping uses CurrentItem and rowToAdd
            self.assertNotIn('currentJToken', robin)
            self.assertIn("Variables.AddRowToDataTable.AppendRowToDataTable DataTable: dtPosts RowToAdd:", robin)

            # 7. Excel workbook and sheet setup
            self.assertIn("IF (File.IfFile.Exists File: excelPath) THEN", robin)
            self.assertIn("Excel.LaunchExcel.LaunchAndOpen Path: excelPath Visible: True ReadOnly: False LoadAddInsAndMacros: False Instance=> ExcelInstance", robin)
            self.assertIn("Excel.LaunchExcel.Launch Visible: True LoadAddInsAndMacros: False Instance=> ExcelInstance", robin)
            self.assertIn("Excel.SetActiveWorksheet.ActivateWorksheetByName", robin)
            self.assertIn("Excel.WriteToExcel.WriteCell Instance: ExcelInstance Value: dtPosts Column: 1 Row: 2", robin)
            self.assertIn("Excel.CloseExcel.CloseAndSaveAs Instance: ExcelInstance DocumentFormat: Excel.ExcelFormat.FromExtension DocumentPath: excelPath", robin)

    def test_real_data_employee_onboarding(self):
        pkg_path = "data/EmployeeOnboardingBot.1.0.1 2.nupkg"
        if os.path.exists(pkg_path):
            with open(pkg_path, "rb") as f:
                proj = self.pm.process_zip_bytes(f.read())
            self.assertEqual(proj.name, "EmployeeOnboardingBot")
            self.assertEqual(proj.total_unmapped, 0)
            robin = self.pm.get_full_project_robin(proj)
            self.assertIn("Excel.LaunchExcel.LaunchAndOpen Path: $'''Employees.xlsx'''", robin)
            self.assertIn("SWITCH department", robin)
            self.assertNotIn("New System.Data.DataTable", robin)
            self.assertNotIn("END SWITCH", robin)
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

    def test_sanitize_strips_html_entities_and_anchor_links(self):
        corrupted = "\n".join([
            "Variables.ConvertJsonToCustomObject Json: $'''{}''' CustomObject=&gt; jsonObj",
            "Web.InvokeWebService.InvokeWebService Url: $'''<a href=\"https://jsonplaceholder.typicode.com/posts\">https://jsonplaceholder.typicode.com/posts</a>''' Method: Web.Method.Get Response=&gt; responseString StatusCode=&gt; responseStatus",
            "Web.InvokeWebService.InvokeWebService Url: $'''<a href=\"https://jsonplaceholder.typicode.com/posts?userId=1&amp;mode=active\">https://jsonplaceholder.typicode.com/posts?userId=1&amp;mode=active</a>''' Method: Web.Method.Get StatusCode=&gt; responseStatus",
            "IF responseStatus &lt; 200 OR responseStatus &gt;= 300 THEN",
            "    Display.ShowMessageDialog.ShowMessage Title: $'''API Error''' Message: $'''Failed''' Icon: Display.Icon.Error Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=&gt; ButtonPressed",
            "END",
        ])
        cleaned = sanitize_robin_script(corrupted)
        expected = "\n".join([
            "Variables.ConvertJsonToCustomObject Json: $'''{}''' CustomObject=> jsonObj",
            "Web.InvokeWebService.InvokeWebService Url: $'''https://jsonplaceholder.typicode.com/posts''' Method: Web.Method.Get Response=> responseString StatusCode=> responseStatus",
            "Web.InvokeWebService.InvokeWebService Url: $'''https://jsonplaceholder.typicode.com/posts?userId=1&mode=active''' Method: Web.Method.Get StatusCode=> responseStatus",
            "IF responseStatus < 200 OR responseStatus >= 300 THEN",
            "    Display.ShowMessageDialog.ShowMessage Title: $'''API Error''' Message: $'''Failed''' Icon: Display.Icon.Error Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=> ButtonPressed",
            "END",
        ])
        self.assertEqual(cleaned, expected)

        br_corrupted = (
            "SET x TO $''''''<br>\u00a0<br/>"
            "Display.InputDialog Title: $'''Age''' UserInput=&gt; age ButtonPressed=&gt; ButtonPressed&lt;br /&gt;"
            "IF age &gt;= 18 THEN<br>END"
        )
        br_cleaned = sanitize_robin_script(br_corrupted, preserve_blank_lines=True)
        self.assertNotIn("<br", br_cleaned.lower())
        self.assertNotIn("\u00a0", br_cleaned)
        self.assertNotIn("&gt;", br_cleaned)
        self.assertEqual(
            br_cleaned,
            "SET x TO $''''''\n\nDisplay.InputDialog Title: $'''Age''' UserInput=> age ButtonPressed=> ButtonPressed\nIF age >= 18 THEN\nEND",
        )

    def test_node_metadata_format_matches_app_output(self):
        pm_meta = ProjectManager(include_node_metadata=True)
        pkg_path = "data/AgeChecker.1.0.1 4.nupkg"
        if os.path.exists(pkg_path):
            with open(pkg_path, "rb") as f:
                proj = pm_meta.process_zip_bytes(f.read())
            robin = pm_meta.get_clean_pasteable_robin(proj)
            self.assertRegex(
                robin,
                r"# node_id=AgeChecker\.00001\.[0-9a-f]{8}; package=String; action=assign; resolved=assign\nSET userAgeText TO \$''''''",
            )
            self.assertRegex(
                robin,
                r"\n\n# node_id=AgeChecker\.00002\.[0-9a-f]{8}; package=Display; action=inputDialog; resolved=input dialog\nDisplay\.InputDialog ",
            )
            self.assertIn("package=Text; action=toNumber; resolved=convert text to number", robin)
            self.assertNotIn("# POWER AUTOMATE DESKTOP", robin)

        xaml = """<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
          <Sequence DisplayName="Main">
            <Sequence.Variables>
              <Variable x:TypeArguments="x:String" Name="FolderPath" Default="C:\\Users\\demo\\Downloads" />
              <Variable x:TypeArguments="x:String" Name="ExcelFilePath1" Default="[FolderPath + &quot;\\FileCleanupPlan.xlsx&quot;]" />
            </Sequence.Variables>
          </Sequence>
        </Activity>"""
        proj_single = pm_meta.process_single_xaml(xaml, filename="Excel_FileCleanup_Tracker.xaml")
        robin_single = pm_meta.get_clean_pasteable_robin(proj_single)
        self.assertRegex(
            robin_single,
            r"# node_id=Excel_FileCleanup_Tracker\.00001\.[0-9a-f]{8}; package=String; action=assign; resolved=assign\nSET FolderPath TO ",
        )
        self.assertRegex(
            robin_single,
            r"\n\n# node_id=Excel_FileCleanup_Tracker\.00002\.[0-9a-f]{8}; package=File; action=assign; resolved=assign\nSET ExcelFilePath1 TO ",
        )

        # Ensure sanitize_robin_script preserves # node_id and blank lines when requested while fixing HTML
        corrupted = (
            "# node_id=Test.00001.a1b2c3d4; package=Web; action=invokeWebService; resolved=invoke web service\n"
            "Web.InvokeWebService.InvokeWebService Url: $'''<a href=\"https://example.com\">https://example.com</a>''' Response=&gt; out\n\n"
            "# node_id=Test.00002.e5f6a7b8; package=If; action=if; resolved=if\n"
            "IF out &lt;&gt; $'''''' THEN\nEND"
        )
        fixed = sanitize_robin_script(corrupted, keep_node_metadata=True, preserve_blank_lines=True)
        self.assertIn("# node_id=Test.00001.a1b2c3d4; package=Web", fixed)
        self.assertIn("\n\n# node_id=Test.00002.e5f6a7b8; package=If", fixed)
        self.assertNotIn("<a href", fixed)
        self.assertNotIn("&gt;", fixed)
        self.assertNotIn("&lt;", fixed)
        self.assertIn("Response=> out", fixed)

    def test_html_sanitization_is_backend_only(self):
        # Frontends must not expose the HTML-cleanup widget or run sanitize_robin_script directly
        for frontend in ("app.py", "app_llm.py"):
            with open(frontend, encoding="utf-8") as f:
                src = f.read()
            self.assertNotIn("Fix / Clean HTML-Corrupted Robin Script", src)
            self.assertNotIn("sanitize_robin_script", src)

        # Pure Python backend sanitizes workflow outputs (including wf.robin_script & clean pasteable output)
        xaml = """<Activity xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
          xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
          <Sequence DisplayName="Main">
            <Sequence.Variables>
              <Variable x:TypeArguments="x:String" Name="apiUrl" Default="https://example.com" />
            </Sequence.Variables>
            <Assign DisplayName="Assign URL">
              <Assign.To><OutArgument x:TypeArguments="x:String">[apiUrl]</OutArgument></Assign.To>
              <Assign.Value><InArgument x:TypeArguments="x:String">[&quot;&lt;a href=&quot;https://example.com/posts&quot;&gt;https://example.com/posts&lt;/a&gt;&quot;]</InArgument></Assign.Value>
            </Assign>
          </Sequence>
        </Activity>"""
        pm = ProjectManager(include_node_metadata=True)
        proj = pm.process_single_xaml(xaml, filename="Main.xaml")
        wf_script = proj.workflows[0].robin_script
        clean_script = pm.get_clean_pasteable_robin(proj)
        for out in (wf_script, clean_script):
            self.assertIn("https://example.com/posts", out)
            self.assertNotIn("<a href", out)
            self.assertNotIn("</a>", out)

        # LLM backend automatically strips HTML entities and anchor tags
        corrupted_json = json.dumps({
            "summary": "Calls API.",
            "robin_script": (
                "Web.InvokeWebService.InvokeWebService "
                "Url: $'''<a href=\"https://jsonplaceholder.typicode.com/posts\">https://jsonplaceholder.typicode.com/posts</a>''' "
                "StatusCode=&gt; responseStatus\n"
                "IF responseStatus &lt; 200 OR responseStatus &gt;= 300 THEN\n"
                "END"
            ),
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": corrupted_json}]}}]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("llm.requests.post", return_value=mock_resp), patch(
                "llm.Path", side_effect=lambda p: __import__("pathlib").Path(tmpdir) / p
            ):
                res = llm.convert_to_robin("test-key", "gemini-2.0-flash", "<Activity/>", [], temperature=0.0)
        self.assertTrue(res["success"])
        self.assertIn("Url: $'''https://jsonplaceholder.typicode.com/posts'''", res["robin_script"])
        self.assertIn("StatusCode=> responseStatus", res["robin_script"])
        self.assertIn("IF responseStatus < 200 OR responseStatus >= 300 THEN", res["robin_script"])
        self.assertNotIn("<a href", res["robin_script"])
        self.assertNotIn("&gt;", res["robin_script"])
        self.assertNotIn("&lt;", res["robin_script"])

    def test_llm_node_metadata_matches_pure_python(self):
        # Verify app_llm.py enables # node_id metadata option by default and forwards it
        with open("app_llm.py", encoding="utf-8") as f:
            app_llm_src = f.read()
        self.assertIn("Include # node_id metadata lines", app_llm_src)
        self.assertIn("include_node_metadata=include_node_metadata", app_llm_src)

        xml_context = (
            "================================================================================\n"
            "FILE: project.json\n"
            "================================================================================\n"
            '{"name": "AgeChecker"}\n\n'
            "================================================================================\n"
            "WORKFLOW XAML FILE: Main.xaml\n"
            "================================================================================\n"
            '<Variable x:TypeArguments="x:String" Name="userAgeText" />\n'
            '<Variable x:TypeArguments="x:Int32" Name="retryCount" />\n'
        )
        llm_json = json.dumps({
            "summary": "Checks user age.",
            "robin_script": "\n".join([
                "# POWER AUTOMATE DESKTOP (ROBIN SCRIPT)",
                "# node_id=WrongName.99999.deadbeef; package=Unknown; action=x; resolved=x",
                "SET userAgeText TO $''''''",
                "SET retryCount TO 1",
                "Display.InputDialog Title: $'''Age''' Message: $'''Enter''' InputType: Display.InputType.SingleLine IsTopMost: False UserInput=> userAgeText ButtonPressed=&gt; ButtonPressed",
                "IF ButtonPressed = $'''OK''' THEN",
                "    Text.ToNumber Text: userAgeText Number=&gt; userAgeText_Num",
                "    IF userAgeText_Num &gt;= 18 THEN",
                "        Display.ShowMessageDialog.ShowMessage Title: $'''Msg''' Message: $'''Adult''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=&gt; ButtonPressed",
                "    ELSE",
                "        Display.ShowMessageDialog.ShowMessage Title: $'''Msg''' Message: $'''Minor''' Icon: Display.Icon.None Buttons: Display.Buttons.OK DefaultButton: Display.DefaultButton.Button1 IsTopMost: False ButtonPressed=&gt; ButtonPressed",
                "    END",
                "END",
            ]),
        })
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": llm_json}]}}]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("llm.requests.post", return_value=mock_resp), patch(
                "llm.Path", side_effect=lambda p: __import__("pathlib").Path(tmpdir) / p
            ):
                res = llm.convert_to_robin(
                    "test-key",
                    "gemini-2.0-flash",
                    xml_context,
                    [],
                    temperature=0.0,
                    include_node_metadata=True,
                )

        self.assertTrue(res["success"])
        out = res["robin_script"]
        self.assertNotIn("WrongName.99999", out)
        self.assertNotIn("&gt;", out)
        self.assertNotIn("POWER AUTOMATE DESKTOP", out)
        self.assertRegex(
            out,
            r"# node_id=AgeChecker\.00001\.[0-9a-f]{8}; package=String; action=assign; resolved=assign\nSET userAgeText TO \$''''''",
        )
        self.assertRegex(
            out,
            r"\n\n# node_id=AgeChecker\.00002\.[0-9a-f]{8}; package=Number; action=assignToNumber; resolved=assign\nSET retryCount TO 1",
        )
        self.assertRegex(
            out,
            r"\n\n# node_id=AgeChecker\.00003\.[0-9a-f]{8}; package=Display; action=inputDialog; resolved=input dialog\nDisplay\.InputDialog ",
        )
        self.assertIn("package=Text; action=toNumber; resolved=convert text to number", out)
        self.assertIn("package=MessageBox; action=messageBox; resolved=show message", out)
        self.assertIn("ButtonPressed=> ButtonPressed", out)

    def test_no_bare_percent_tokens_or_invalid_pad_actions_across_all_packages(self):
        pad_string_re = re.compile(r"\$'''(?:(?!''').)*'''")
        invalid_tokens = (
            "FlowControl.StopFlow",
            "LaunchBlank",
            "FirstRowIsHeader",
            "Flow.RunFlow",
            "END SWITCH",
            "New System.Data",
        )
        html_tokens = ("<br", "&gt;", "&lt;", "&amp;", "<a ", "\u00a0")
        packages = sorted(glob.glob("data/*.nupkg") + glob.glob("sample_bots/*.zip"))
        self.assertTrue(packages)

        for pkg_path in packages:
            for include_meta in (False, True):
                pm = ProjectManager(include_node_metadata=include_meta)
                with open(pkg_path, "rb") as f:
                    proj = pm.process_zip_bytes(f.read(), os.path.basename(pkg_path))
                robin = pm.get_full_project_robin(proj)
                for line in robin.splitlines():
                    for tok in invalid_tokens:
                        self.assertNotIn(tok, line, msg=f"{pkg_path}: invalid token {tok} in {line}")
                    for tok in html_tokens:
                        self.assertNotIn(tok, line, msg=f"{pkg_path}: HTML token {tok} in {line}")
                    stripped = pad_string_re.sub("", line)
                    if not stripped.lstrip().startswith("#"):
                        self.assertNotIn("%", stripped, msg=f"{pkg_path}: bare % outside quotes in {line}")

        tagged = apply_robin_node_metadata("EXIT Code: 0\nSWITCH department", workflow_name="CrudOperation")
        self.assertIn("package=FlowControl; action=stopFlow; resolved=stop flow\nEXIT Code: 0", tagged)
        self.assertIn("package=Switch; action=switch; resolved=switch\nSWITCH department", tagged)

    def test_app_llm_exposes_endpoint_model_and_api_key_ui(self):
        with open("app_llm.py", encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"Endpoint"', src)
        self.assertIn('"Model"', src)
        self.assertIn('"API Key"', src)
        self.assertIn("endpoint=endpoint", src)
        self.assertIn("PROVIDER_PRESETS", src)

    def test_llm_custom_endpoints_routing(self):
        openai_json = json.dumps({
            "summary": "Custom endpoint conversion.",
            "robin_script": "SET x TO $'''ok'''",
        })
        gemini_resp = MagicMock()
        gemini_resp.status_code = 200
        gemini_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": openai_json}]}}]
        }
        openai_resp = MagicMock()
        openai_resp.status_code = 200
        openai_resp.json.return_value = {
            "choices": [{"message": {"content": openai_json}}]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = lambda p: __import__("pathlib").Path(tmpdir) / p

            # 1. Localhost OpenAI-compatible endpoint allows empty API key
            with patch("llm.requests.post", return_value=openai_resp) as mock_post, patch(
                "llm.Path", side_effect=temp_path
            ):
                res = llm.convert_to_robin(
                    "",
                    "llama3.1",
                    "<Activity/>",
                    [],
                    endpoint="http://localhost:11434/v1",
                )
            self.assertTrue(res["success"])
            self.assertEqual(res["endpoint_used"], "http://localhost:11434/v1/chat/completions")
            self.assertEqual(mock_post.call_args.args[0], "http://localhost:11434/v1/chat/completions")

            # 2. Remote OpenRouter endpoint routes Gemini model name to /chat/completions
            with patch("llm.requests.post", return_value=openai_resp) as mock_post, patch(
                "llm.Path", side_effect=temp_path
            ):
                res = llm.convert_to_robin(
                    "or-key",
                    "google/gemini-2.0-flash-001",
                    "<Activity/>",
                    [],
                    endpoint="https://openrouter.ai/api/v1",
                )
            self.assertTrue(res["success"])
            self.assertEqual(mock_post.call_args.args[0], "https://openrouter.ai/api/v1/chat/completions")
            self.assertEqual(mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer or-key")

            # 3. Azure OpenAI uses api-key header and deployment URL
            with patch("llm.requests.post", return_value=openai_resp) as mock_post, patch(
                "llm.Path", side_effect=temp_path
            ):
                res = llm.convert_to_robin(
                    "az-key",
                    "my-gpt4o",
                    "<Activity/>",
                    [],
                    endpoint="https://contoso.openai.azure.com",
                )
            self.assertTrue(res["success"])
            self.assertIn("/openai/deployments/my-gpt4o/chat/completions", mock_post.call_args.args[0])
            self.assertEqual(mock_post.call_args.kwargs["headers"]["api-key"], "az-key")

            # 4. Custom Gemini endpoint appends key and calls exact URL
            with patch("llm.requests.post", return_value=gemini_resp) as mock_post, patch(
                "llm.Path", side_effect=temp_path
            ):
                res = llm.convert_to_robin(
                    "gem-key",
                    "gemini-2.0-flash",
                    "<Activity/>",
                    [],
                    endpoint="https://proxy.example.com/v1beta/models/gemini-2.0-flash:generateContent",
                )
            self.assertTrue(res["success"])
            self.assertEqual(
                mock_post.call_args.args[0],
                "https://proxy.example.com/v1beta/models/gemini-2.0-flash:generateContent?key=gem-key",
            )

            # 5. Remote endpoint rejects empty API key cleanly
            err_res = llm.convert_to_robin("", "gpt-4o", "<Activity/>", [], endpoint="https://api.openai.com/v1")
            self.assertFalse(err_res["success"])
            self.assertIn("API Key is required", err_res["error"])

if __name__ == "__main__":
    unittest.main()
