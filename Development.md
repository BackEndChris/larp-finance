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

Since testing's been done and connection has been established to be working, it's time to move the database work inside the source code right beside main.py. Database.py is gonna be the engine creator that lets this project's code communicate with our database. Later we can then improve configurations but for now establishing the connection is enough. 

Next thing to work on would be helping the database know the data that it should store. Anything that would be important and related to the user, since making it work is the priority adding the app specific features like portfolios or balances shall be instead added later on. Incorporating ORM for convenience instead of sticking to direct SQL queries that would have to be configured on the database itself. 

Since we're already at configuring and creating databases, the project shall now be incorporating Alembic as well to keep track of changes to the database structure. 

Configuration using alembic was successful. The users table has now been created in the database without being configured directly which is really convenient all the more for future configurations in the database and code that affects said database. 

Signed: 5th Commit "Feat: Add User ORM model and initial Alembic migration"

Enough configurations have been set in the database section, moving onto finally working our way into user registration. Added schemas.py for API data validation, to ensure people are gonna be writing the right inputs and if not, ideally, the request shouldn't go through. Security.py for incorporating password hashing using Argon2id through pwdlib and finally adding the user registration endpoint as well as testing if everything works via Swagger UI. Password hashing in particular has been verified directly in PostgreSQL for safety purposes.   

Added some more database related configurations as well for future convenience like get_db() to manage database sessions. 

For now the registration endpoint checks for duplicate usernames and emails, returning HTTP 409 whenever necessary and HTTP 422 if users put invalid email inputs instead. If more checks would be deemed necessary, they will probably be added later. 

Signed: 6th Commit "Feat: Implement User Registration and Password Hashing"

Onto the next thing, if users can register. Then users should be able to log in. Configured schemas to accept UserLogin data entries and tested if said endpoint is working properly. It worked properly, endpoint confirmed to be verifying UserName and hashed password properly. Next was JWT implementation to grant access tokens to each subsequent unique user per log in session. Really important for user specific tasks and requests that are planned. JWT implementation, tested. Everything was working. 

Signed: 7th Commit "Feat: Login Auth and JWT Token Generation"

Added authentication that makes use of the previously added JWT implementation as well as a new user specific GET endpoint that tests if the JWT implementation and log in functions are working properly. Dependency injection through reusable get_current_user() has also been implemented in auth.py so that secure endpoints can reuse the same authetication logic. 

The JWT verification for now verifies the JWT signature using a pre composed key, checks if the token hasn't expired, extracts the user's ID and retrieves the matching account from PostgreSQL. 

Signed: 8th Commit "Feat: Added JWT Verification and Protected User Endpoint"