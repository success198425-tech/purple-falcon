"""Launch Purple Falcon with the integrated analysis tab.

Run:
    python purple_falcon_app.py
"""
import inspect

from falcon_ultimate import (
    DEFAULT_THEME,
    STYLE,
    _blocks_takes_style,
    demo,
    make_favicon,
)
from analysis_ui import add_analysis_tab

add_analysis_tab(demo)

if __name__ == "__main__":
    launch_params = inspect.signature(demo.launch).parameters
    launch_style = {} if _blocks_takes_style else {
        k: v for k, v in STYLE.items() if k in launch_params
    }
    favicon = make_favicon()
    if favicon and "favicon_path" in launch_params:
        launch_style["favicon_path"] = favicon
    demo.launch(
        server_name="127.0.0.1",
        share=__import__("os").getenv("PF_SHARE", "0") == "1",
        show_error=True,
        **launch_style,
    )
