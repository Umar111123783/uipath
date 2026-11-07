import zipfile
import xml.etree.ElementTree as ET

def inspect_pkg(pkg_path):
    print("=" * 60)
    print("INSPECTING:", pkg_path)
    with zipfile.ZipFile(pkg_path, 'r') as z:
        for name in z.namelist():
            if name.endswith('.xaml'):
                print(f"\n--- {name} ---")
                text = z.read(name).decode('utf-8', errors='ignore')
                root = ET.fromstring(text)
                
                for elem in root.iter():
                    t = elem.tag.split('}')[-1]
                    # Print interesting activity tags and their properties
                    if t in [
                        'InputDialog', 'HttpClient', 'NetHttpRequest', 'DeserializeJson',
                        'DeserializeJsonArray', 'BuildDataTable', 'AddDataRow',
                        'ExcelProcessScopeX', 'ExcelApplicationCard', 'ReadRangeX',
                        'WriteRangeX', 'Switch', 'ShowFormActivity', 'ForEachRow', 'ForEach', 'If'
                    ]:
                        disp = elem.attrib.get('DisplayName', '')
                        props = {k: v for k, v in elem.attrib.items() if not k.startswith('{')}
                        print(f"Tag: {t} | DisplayName: '{disp}'")
                        print(f"  Attribs: {props}")
                        # check child tags
                        children = [c.tag.split('}')[-1] for c in elem]
                        if children:
                            print(f"  Child tags: {children}")

if __name__ == '__main__':
    inspect_pkg('data/AgeChecker.1.0.1 4.nupkg')
    inspect_pkg('data/CrudOperation.1.0.1 2.nupkg')
    inspect_pkg('data/EmployeeOnboardingBot.1.0.1 2.nupkg')

