"""Entry point for `streamlit run app.py` (and Streamlit Community Cloud): runs app/streamlit_app.py."""
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "app"))
runpy.run_path(str(Path(__file__).parent / "app" / "streamlit_app.py"), run_name="__main__")
