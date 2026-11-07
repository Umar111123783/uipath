import os
import zipfile
import json

def create_sample_bots(output_dir="sample_bots"):
    os.makedirs(output_dir, exist_ok=True)
    
    # -------------------------------------------------------------
    # Sample 1: Web Search & Extraction Bot
    # -------------------------------------------------------------
    web_bot_name = "UiPath_Web_Search_Bot"
    web_zip_path = os.path.join(output_dir, f"{web_bot_name}.zip")
    
    web_project_json = {
        "name": "UiPath_Web_Search_Bot",
        "description": "Automated Google search and result extraction with logging subflow",
        "main": "Main.xaml",
        "schemaVersion": "4.0",
        "targetFramework": "Windows",
        "dependencies": {
            "UiPath.UIAutomation.Activities": "[22.10.4]",
            "UiPath.System.Activities": "[22.10.3]"
        }
    }
    
    web_main_xaml = '''<Activity mc:Ignorable="sap sap2010" x:Class="Main"
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:sap="http://schemas.microsoft.com/netfx/2009/xaml/activities/presentation"
  xmlns:sap2010="http://schemas.microsoft.com/netfx/2010/xaml/activities/presentation"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Main Google Search Sequence">
    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="searchQuery" Default="Power Automate Desktop Robin Language" />
      <Variable x:TypeArguments="x:String" Name="extractedStats" Default="" />
      <Variable x:TypeArguments="x:Int32" Name="waitSeconds" Default="3" />
    </Sequence.Variables>
    
    <ui:LogMessage DisplayName="Log Start" Level="Info" Message="[&quot;Starting web search for query: &quot; + searchQuery]" />
    
    <ui:OpenBrowser BrowserType="Chrome" DisplayName="Launch Google Chrome" Url="https://www.google.com">
      <ui:OpenBrowser.Body>
        <ActivityAction x:TypeArguments="x:Object">
          <ActivityAction.Argument>
            <DelegateInArgument x:TypeArguments="x:Object" Name="ContextTarget" />
          </ActivityAction.Argument>
          <Sequence DisplayName="Search Actions Sequence">
            <ui:TypeInto DisplayName="Type Search Term" Text="[searchQuery]">
              <ui:TypeInto.Target>
                <ui:Target Selector="&lt;html app='chrome.exe' title='Google' /&gt;&lt;webctrl tag='INPUT' name='q' /&gt;" />
              </ui:TypeInto.Target>
            </ui:TypeInto>
            <ui:Click DisplayName="Click Search Button">
              <ui:Click.Target>
                <ui:Target Selector="&lt;html app='chrome.exe' title='Google' /&gt;&lt;webctrl tag='INPUT' name='btnK' type='submit' /&gt;" />
              </ui:Click.Target>
            </ui:Click>
            <Delay DisplayName="Wait For Results Load" Duration="00:00:03" />
            <ui:GetValue DisplayName="Extract Result Statistics">
              <ui:GetValue.Target>
                <ui:Target Selector="&lt;html app='chrome.exe' /&gt;&lt;webctrl tag='DIV' id='result-stats' /&gt;" />
              </ui:GetValue.Target>
              <ui:GetValue.Value>
                <OutArgument x:TypeArguments="x:String">[extractedStats]</OutArgument>
              </ui:GetValue.Value>
            </ui:GetValue>
            <ui:CloseTab DisplayName="Close Search Browser Tab" />
          </Sequence>
        </ActivityAction>
      </ui:OpenBrowser.Body>
    </ui:OpenBrowser>
    
    <If Condition="[extractedStats &lt;&gt; &quot;&quot;]" DisplayName="Check Stats Extracted">
      <If.Then>
        <Sequence DisplayName="Success Handling">
          <ui:MessageBox Caption="Search Result" DisplayName="Display Search Result" Text="[&quot;Extracted stats: &quot; + extractedStats]" />
          <ui:InvokeWorkflowFile WorkflowFileName="LogResults.xaml" DisplayName="Record In Log Subflow" />
        </Sequence>
      </If.Then>
      <If.Else>
        <ui:LogMessage DisplayName="Log Warning" Level="Warn" Message="[&quot;No search statistics extracted&quot;]" />
      </If.Else>
    </If>
  </Sequence>
</Activity>'''

    web_sub_xaml = '''<Activity mc:Ignorable="sap sap2010" x:Class="LogResults"
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <x:Members>
    <x:Property Name="in_LogMessage" Type="InArgument(x:String)" />
  </x:Members>
  <Sequence DisplayName="Log Results Subflow">
    <ui:AppendText DisplayName="Append to Search Audit File" FileName="C:\\Logs\\SearchHistory.txt" Text="Search executed successfully at runtime." />
    <ui:LogMessage DisplayName="Confirm Log" Level="Info" Message="Audit history updated." />
  </Sequence>
</Activity>'''

    with zipfile.ZipFile(web_zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(web_project_json, indent=2))
        z.writestr("Main.xaml", web_main_xaml)
        z.writestr("LogResults.xaml", web_sub_xaml)

    # -------------------------------------------------------------
    # Sample 2: Excel & Data Processing Bot
    # -------------------------------------------------------------
    excel_bot_name = "UiPath_Excel_Processor_Bot"
    excel_zip_path = os.path.join(output_dir, f"{excel_bot_name}.zip")
    
    excel_project_json = {
        "name": "UiPath_Excel_Processor_Bot",
        "description": "Reads customer Excel sheet, loops through rows, updates status and saves workbook",
        "main": "Main.xaml",
        "schemaVersion": "4.0",
        "targetFramework": "Windows",
        "dependencies": {
            "UiPath.Excel.Activities": "[2.16.0]",
            "UiPath.System.Activities": "[22.10.3]"
        }
    }
    
    excel_main_xaml = '''<Activity mc:Ignorable="sap sap2010" x:Class="Main"
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="Process Customer Excel Records">
    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="excelFilePath" Default="C:\\Data\\Customers.xlsx" />
      <Variable x:TypeArguments="x:String" Name="customersTable" Default="" />
      <Variable x:TypeArguments="x:Int32" Name="rowCount" Default="0" />
    </Sequence.Variables>
    
    <ui:LogMessage DisplayName="Log Start" Level="Info" Message="[&quot;Opening customer workbook: &quot; + excelFilePath]" />
    
    <ui:ExcelApplicationScope WorkbookPath="[excelFilePath]" DisplayName="Excel Scope - Customers" Visible="True">
      <ui:ExcelApplicationScope.Body>
        <ActivityAction x:TypeArguments="ui:WorkbookApplication">
          <ActivityAction.Argument>
            <DelegateInArgument x:TypeArguments="ui:WorkbookApplication" Name="WorkbookScope" />
          </ActivityAction.Argument>
          <Sequence DisplayName="Excel Operations Sequence">
            <ui:ExcelReadRange DataTable="[customersTable]" DisplayName="Read All Customers" SheetName="Sheet1" Range="A1:G100" />
            <ui:ForEachRow CurrentIndex="[rowCount]" DataTable="[customersTable]" DisplayName="Iterate Customer Rows">
              <ActivityAction x:TypeArguments="x:Object">
                <Sequence DisplayName="Process Row Action">
                  <Assign DisplayName="Increment Processed Count">
                    <Assign.To>
                      <OutArgument x:TypeArguments="x:Int32">[rowCount]</OutArgument>
                    </Assign.To>
                    <Assign.Value>
                      <InArgument x:TypeArguments="x:Int32">[rowCount + 1]</InArgument>
                    </Assign.Value>
                  </Assign>
                  <If Condition="[rowCount &gt; 50]" DisplayName="Check Batch Limit">
                    <If.Then>
                      <ui:Break DisplayName="Exit Loop on Limit" />
                    </If.Then>
                  </If>
                </Sequence>
              </ActivityAction>
            </ui:ForEachRow>
            <ui:ExcelWriteRange DataTable="[customersTable]" DisplayName="Write Output Range" SheetName="Summary" StartingCell="A1" />
            <ui:ExcelSaveWorkbook DisplayName="Save Excel Document" />
          </Sequence>
        </ActivityAction>
      </ui:ExcelApplicationScope.Body>
    </ui:ExcelApplicationScope>
    
    <ui:MessageBox Caption="Success" DisplayName="Notify Completion" Text="[&quot;Successfully processed &quot; + rowCount.ToString() + &quot; customer records.&quot;]" />
  </Sequence>
</Activity>'''

    with zipfile.ZipFile(excel_zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(excel_project_json, indent=2))
        z.writestr("Main.xaml", excel_main_xaml)

    # -------------------------------------------------------------
    # Sample 3: Desktop App & File Automation Bot
    # -------------------------------------------------------------
    file_bot_name = "UiPath_File_Automation_Bot"
    file_zip_path = os.path.join(output_dir, f"{file_bot_name}.zip")
    
    file_project_json = {
        "name": "UiPath_File_Automation_Bot",
        "description": "Backup folder creation, file copy, Notepad process launch and kill",
        "main": "Main.xaml",
        "schemaVersion": "4.0",
        "targetFramework": "Windows",
        "dependencies": {
            "UiPath.System.Activities": "[22.10.3]"
        }
    }
    
    file_main_xaml = '''<Activity mc:Ignorable="sap sap2010" x:Class="Main"
  xmlns="http://schemas.microsoft.com/netfx/2009/xaml/activities"
  xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
  xmlns:ui="http://schemas.uipath.com/workflow/activities"
  xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <Sequence DisplayName="System and File Automation Routine">
    <Sequence.Variables>
      <Variable x:TypeArguments="x:String" Name="sourceFile" Default="C:\\Reports\\MonthlySummary.txt" />
      <Variable x:TypeArguments="x:String" Name="backupFolder" Default="C:\\Backup\\Monthly" />
      <Variable x:TypeArguments="x:String" Name="fileContent" Default="" />
    </Sequence.Variables>
    
    <ui:CreateDirectory DisplayName="Create Backup Directory" Path="[backupFolder]" />
    <ui:WriteTextFile DisplayName="Create Initial Report File" FileName="[sourceFile]" Text="Initial Report Header: 2026 Monthly Summary" />
    <ui:ReadTextFile Content="[fileContent]" DisplayName="Read Report Content" FileName="[sourceFile]" />
    <ui:CopyFile Destination="[backupFolder + &quot;\\MonthlySummary_Backup.txt&quot;]" DisplayName="Copy to Backup Folder" Overwrite="True" Path="[sourceFile]" />
    <ui:StartProcess Arguments="[sourceFile]" DisplayName="Open in Notepad Editor" FileName="notepad.exe" />
    <Delay DisplayName="Wait 5 Seconds For Inspection" Duration="00:00:05" />
    <ui:KillProcess DisplayName="Terminate Notepad Process" ProcessName="notepad" />
    <ui:MessageBox Caption="Automation Finished" DisplayName="Final Alert" Text="File backup and inspection cycle completed successfully." />
  </Sequence>
</Activity>'''

    with zipfile.ZipFile(file_zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr("project.json", json.dumps(file_project_json, indent=2))
        z.writestr("Main.xaml", file_main_xaml)
        
    print(f"Sample bots created in {output_dir}:")
    print(f" - {web_zip_path}")
    print(f" - {excel_zip_path}")
    print(f" - {file_zip_path}")

if __name__ == "__main__":
    create_sample_bots()

