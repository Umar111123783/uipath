import unittest
import os
from converter.project_manager import ProjectManager
from converter.selector_parser import build_parsed_selector
from converter.expression_parser import (
    convert_uipath_expression_to_robin,
    convert_uipath_condition_to_robin,
    parse_uipath_duration
)

class TestUiPathToRobinConverter(unittest.TestCase):

    def setUp(self):
        self.pm = ProjectManager(include_comments=True, include_selectors_header=True)

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
            robin = self.pm.get_full_project_robin(proj)
            self.assertIn("Display.InputDialog", robin)
            self.assertIn("IF userAgeText >= 18 THEN", robin)

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

            # 6. DataTable row mapping uses CurrentItem and rowValues list
            self.assertNotIn('currentJToken', robin)
            self.assertIn("Variables.AddItemToList Item: CurrentItem['userId'] List: rowValues", robin)
            self.assertIn("Variables.AddRowToDataTable.AppendRowToDataTable DataTable: dtPosts RowToInsert: rowValues", robin)

            # 7. Excel workbook and sheet setup
            self.assertIn("File.IfFile.Exists File: %excelPath% THEN", robin)
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

if __name__ == "__main__":
    unittest.main()
