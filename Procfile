web: gunicorn views:app -w 3 --timeout 60 --reload
run_all: python update.py Crossref.run --chunk=10 --limit=900000000
base_find_fulltext: python update.py Base.find_fulltext --chunk=25 --limit=10000000
run_with_realtime_scraping: python update.py Crossref.run_with_realtime_scraping --chunk=10 --limit=100000000
skip_all_hybrid: python update.py Crossref.run_with_skip_all_hybrid --chunk=10 --limit=100000000
load_test: python load_test.py --limit=50000
