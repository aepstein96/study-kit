"""Analyze the data and write the small artifact the app loads: app/public/data.json."""
import sys
from datetime import datetime, timezone

from research_toolkit import study_root, write_data_json

# Every path hangs off the study dir, resolved from __file__ — never off the process cwd,
# which resets between shell calls and has silently produced sheets of false FAILs.
STUDY = study_root(__file__)
sys.path.insert(0, str(STUDY / "src"))
from connector import fetch  # noqa: E402


def main() -> None:
    raw = fetch()  # noqa: F841  (load + analyze it)

    out = {
        "meta": {
            "title": "Study title",
            "description": "What this shows.",
            "source": "Source name",
            "source_url": "https://…",
            "generated": datetime.now(timezone.utc).isoformat(),
        },
        "stats": [{"label": "Example", "value": 0, "unit": ""}],
        "series": [{"name": "example", "color": "#3574d4", "points": [[0, 0], [1, 1]]}],
        "xLabels": ["a", "b"],
    }

    # Assert the invariants this study relies on right here, so they run free forever
    # (bounds, feasibility, conservation — see the lessons list).

    write_data_json(STUDY, out)


if __name__ == "__main__":
    main()
