from fastapi import FastAPI
from dotenv import load_dotenv
import os

# load environment
load_dotenv()

# import routers
from api import auth_router

# import middleware
from security import JWTAuthMiddleware


def create_app() -> JWTAuthMiddleware:
	app = FastAPI(title="Akilu RAG API")

	# include routers
	app.include_router(auth_router)

	# wrap the app with JWT auth middleware (ASGI middleware)
	app = JWTAuthMiddleware(app)

	return app


app = create_app()


if __name__ == "__main__":
	# simple local run for convenience
	import uvicorn

	host = os.getenv("HOST", "127.0.0.1")
	port = int(os.getenv("PORT", 8080))
	try:
		uvicorn.run("app.main:app", host=host, port=port, reload=True)
	except OSError as e:
		msg = str(e)
		# Windows-specific socket permission error is WinError 10013
		if "10013" in msg or getattr(e, "winerror", None) == 10013:
			print()
			print(f"ERROR: Could not bind to {host}:{port} — permission denied or port in use.")
			print("Attempting to find an alternate port...")
			# Try a range of alternative ports
			tried = []
			success = False
			for p in range(port + 1, port + 11):
				try:
					print(f"Trying port {p}...")
					uvicorn.run("app.main:app", host=host, port=p, reload=True)
					success = True
					break
				except OSError as e2:
					tried.append((p, str(e2)))
					# continue trying
					continue

			if not success:
				print()
				print("Could not bind to any of the alternative ports.")
				print("Checked ports:")
				for p, m in tried:
					print(f" - {p}: {m}")
				print()
				print("Possible causes:")
				print(" - Another process is already listening on the port(s)")
				print(" - Firewall or antivirus is blocking the bind")
				print()
				print("Quick checks (PowerShell):")
				print(f"  netstat -ano | findstr :{port}")
				print("  # or check a specific port")
				print(f"  netstat -ano | findstr :{port + 1}")
				print("  # if you find a PID, show the process")
				print("  tasklist /fi \"PID eq <pid>\"")
				print("  # kill the process (replace <pid>)")
				print("  Stop-Process -Id <pid> -Force")
				print()
				print("Workarounds:")
				print(f" - Run the app on a different port explicitly: set PORT=8001; poetry run python src/app/main.py")
				print(" - Run your terminal as Administrator if binding to a restricted port")
		else:
			print("uvicorn failed to start:", e)


