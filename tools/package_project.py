"""Package portable Python source, weather, literature and verification records."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
destination = root / "outputs" / "kenya-mobile-solar-dashboard.zip"
files = [root/name for name in ["app.py","launch.py","requirements.txt","requirements-dev.txt",
    "README.md","CONTRIBUTING.md","ENGINEERING_NOTES.md","VALIDATION.md","literature.json",".gitignore",".gitattributes"]]
for folder in ["solar_model","tests","tools","data","assets",".streamlit",".github"]:
    files += [p for p in (root/folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
for name in ["nairobi_default.json","tracking_comparison.csv","scenario_comparison.csv","tracking-preview.png"]:
    path = root/"outputs"/name
    if path.exists():
        files.append(path)
destination.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        archive.write(path,Path("kenya-mobile-solar-dashboard")/path.relative_to(root))
print(f"{destination} ({destination.stat().st_size/1024/1024:.2f} MB)")
