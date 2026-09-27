install:  ; pip install -r requirements.txt
fetch:    ; python scripts/fetch_open_data.py
build:    ; python scripts/build_hazard.py
relocate: ; python scripts/plan_relocation.py
backtest: ; python scripts/backtest.py 2000
serve:    ; cd web && python -m http.server 8000
all: fetch build relocate
