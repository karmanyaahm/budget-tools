PORT ?= 8137
HOST ?= buckets.localhost
FILE ?= My Budget.buckets

.DEFAULT_GOAL := web
.PHONY: web clean

# Serve the web app. FILE (default "My Budget.buckets") is exposed to the app as
# web/default.buckets so it auto-loads without a manual upload.
#   make                       # serves "My Budget.buckets"
#   make FILE="path/to/x.buckets"
web:
	@if [ -f "$(FILE)" ]; then \
		ln -sf "$$(cd "$$(dirname "$(FILE)")" && pwd)/$$(basename "$(FILE)")" web/default.buckets; \
		echo "Auto-loading: $(FILE)"; \
	else \
		rm -f web/default.buckets; \
		echo "No file '$(FILE)' — upload one in the browser."; \
	fi
	@echo "Serving web at http://$(HOST):$(PORT)/  (Ctrl-C to stop)"
	@cd web && python3 -m http.server $(PORT) --bind ::1

clean:
	@rm -f budget_*.png budget_pies.png web/default.buckets
	@rm -rf __pycache__
	@echo "cleaned"
