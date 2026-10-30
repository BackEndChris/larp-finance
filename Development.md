Development Documentation File

Goal: 

To develop a meme themed website that incorporates financial ideas like trading, investing etc.

Documentation:

Start, set up or initialize the project folder with uv and create a virtual environment.

Using uv instead of pip to simplify the development workflow by combining virtual environment management and dependency installation. Should make the project easier to reproduce for other developers and eventually in CI/CD and production environments.

Added other files into .gitignore that it might've missed before first commit. 

Signed: First Commit "Initiate Project Larp Finance"

Onto building the skeleton for the API itself, file separation shall be done later but for convenience's sake initialization of FastAPI and creating the endpoints shall happen in main.py.

Added fastapi and wrote at least till the root endpoint, encountered the first problem while trying to add uvicorn into environment. "Failed to remove directory error" encountered, closed my IDE and temporarily stopped syncing any active cloud services (in my case: OneDrive) then it worked. Luckily a quick fix. 

Confirmed that the root endpoint was working as well as fastAPI and uvicorn working properly. Run it through local host with uvicorn, access it with your browser in "http://127.0.0.1:8000". Swagger UI available via "http://127.0.0.1:8000/docs".

Signed: Second Commit "Root Endpoint Created and Dependencies Added"