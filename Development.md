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

Got it out of the cloud space directory as it seems to interfere with the virtual environment that's been set up. Deleted the old .venv to avoid pathing problems and ran uv sync anew to recreate a new .venv and restore the project's dependencies from before the migration. 

Despite uvicorn working as intended inside the cloud space directory, the initial installation failed to completely record it as a project dependency. After migrating and recreating the virtual environment outside the cloud however, said problem was solved. 

Signed: Third Commit "Chore: Restore Environment and Fix Uvicorn Dependency"

Now onto architectural planning, how would the end product look like? Frontend aside, the backend should be able to register and let users log-in to then be able to manage their own portfolios hence, so far in regards to endpoints, at least 1 of each: register, log-in and a get endpoint for them to request their portfolio. For them to have the stocks or coins in question though, I'd need a buy and sell endpoint as well as a "trade" endpoint. To even activate the last endpoints however i'd need at least 2 API Keys from public stock or crypto brokerages. Or maybe just one since the app won't execute real trades? If we can find a good market-data provider that handles both then that's good enough since we won't need brokerage access anyway.

Since the plan is to actually deploy this project, for security purposes Argon2id might be better than bcrypt for password hashing and verification, PyJWT the usual should work fine for verifying authentication tokens. 

Opening up a new database to store users locally for now should probably be taken care of before even going to some of the aforementioned endpoints. 

Database created, name set to larp_finance_dev for now. Adding SQLAlchemy and Psycopg to handle database operations and allow python to communicate with PostgreSQL. 

Onto testing the database connection, adding python-dotenv. Creating a separate db_test python file as well to test the the connection. 

Testing worked, so: Database has been created, connected to python environment using SQLAlchemy and Psycopg then tested.

Signed: 4th Commit "Chore: Establish and verify PostgreSQL connection"