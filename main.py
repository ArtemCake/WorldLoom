# main.py

"""Точка входа WorldLoom."""

from backend.app.application import create_app

app = create_app(enable_file_cleanup=True)

if __name__ == "__main__":
	import uvicorn

	uvicorn.run(
		app,
		host="0.0.0.0",
		port=8080,
		log_level="info",
		proxy_headers=False,
	)