import zipfile
import glob
import xml.etree.ElementTree as ET

def clean_tag(tag):
    return tag.split('}')[-1] if '}' in tag else tag

for pkg in sorted(glob.glob('data/*')):
    print("=" * 80)
    print("ANALYZING PACKAGE:", pkg)
    with zipfile.ZipFile(pkg, 'r') as z:
        for name in z.namelist():
            if name.endswith('.xaml'):
                print(f"\n--- XAML FILE: {name} ---")
                content = z.read(name).decode('utf-8', errors='ignore')
                root = ET.fromstring(content)
                
                def walk(node, depth=0):
                    t = clean_tag(node.tag)
                    if t in ['NamespacesForImplementation', 'ReferencesForImplementation', 
                             'AssemblyReference', 'ViewState', 'ViewStateData', 'Dictionary']:
                        return
                    disp = node.attrib.get('DisplayName', '')
                    attrs_brief = {k: v for k, v in node.attrib.items() if not k.startswith('{') and k != 'DisplayName'}
                    indent = "  " * depth
                    if disp or attrs_brief or t in ['Sequence', 'If', 'ForEach', 'ForEachRow', 'Switch', 'ExcelProcessScopeX', 'ExcelApplicationCard']:
                        print(f"{indent}[{t}] DisplayName='{disp}' Attrs={attrs_brief}")
                    for c in node:
                        walk(c, depth + 1)
                
                walk(root)

if __name__ == "__main__":
    pass

