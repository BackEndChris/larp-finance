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

Next thing is incorporating pytest into the project. The features are adding up and testing things manually one by one are getting inconvenient and impractical. Since we don't want pytest or any of our automated testing messing up with the original database, database isolation will also be pulling through.

Tests are done, everything's successful and ready to be committed again. A whole new folder "Tests" has also been created to sort out the tests and distribute things properly. Same thing is gonna be happening with main.py later since it's doing too much right now but for now this is fine. 

The testing infrastructure uses dependency injection to work through or override the previously set up get_db(), so that the operations can be redirected to the test database instead. Rollbacks have also been introduced so that not every test would create a random test user to stay as a consequence of testing the endpoints or associated features. 

Tests, have also been added for registration, login and JWT authentication. Succesful registrations, duplicate usernames, invalid inputs and a lot more have been tested. So far all 14 tests passed.

This sorts out the project's first automated regression test suite. There are still probably improvements that could be made and tests I could've forgotten but those could be added along the way. At the very least the initial testing infrastructure is now functional. 

Signed: 9th Commit "Test: Added Isolated Authentication Tests with Pytest"

Since the tests have now been incorporated into the project, before pushing everything online to Github, might as well add CI/CD into the project. First CI using GitHub Actions for convenience. Instead of having to manually run pytest every time changes are made, Github should automatically run the tests whenever changes are pushed to the main. Extremely helpful as the project grows and extremely handy our plans for deployment. 

Created the new GitHub repo and connected it to the already existing local Git repo. Added ci.yml to configure an Ubuntu environment, temporary PostgreSQL database and automated pytest execution. Separate JWT secret through GitHub's repo secrets also added. 

The goal is to make sure that the already existing 14 automated tests can run without any troubles outside the local development environment. This commit is pre-testing, if things go as planned then it shall be documented through the 11th Commit.

Signed: 10th Commit "CI: Add GitHub Actions Pytest Workflow"

Hiccup on and about detected, configured ci.yml in hopes of fixing the issue. 

Signed: 11th Commit "Fix: Pin Setup-uv action to valid release"

Issue, fixed. Didn't want to document it till the fix was surely dealt with. The initial GitHub Actions run failed because the specified setup-uv action version couldn't be resolved. Pinning the action to a valid release before pushing the correction to GitHub cleaned the issue. 

The following CI run succeeded, the workflow can execute outside the local Windows environment. 

CI should now be functional and will automatically validate future changes pushed to the main branch. 

Onto the next thing, Portfolio Management. Got the new endpoint added and working, now users who register automatically get 10,000 USD worth of paper money and are able to see this through the new GET endpoint. 

An alembic migration was also taken care of to sync in the new configs needed by our database. 1 user, 1 portfolio. Atomic registration has also been introduced for smooth registrations, using db.flush() and db.commit(), we allow account and portfolio creation to be one database transaction, if something goes wrong somewhere, the whole transaction gets rollbacked, not leaving any half finished traces. 

Subsequently, 3 new automated portfolio tests have also been naturally created, bringing the total tests to 17. All of which have succeeded so far. 

Signed: 12th Commit: "Feat: Added Portfolio Model and Automatic Portfolio Creation"

Going forward to Asset and Holding management. Added 2 new ORM models: Asset and Holding. The former to represent the stocks and coins (cryptocurrencies) supported by the simulator and the latter representing the assets owned by individual users. 

To apply this, a 3rd migration was applied and implemented. Added 7 initial assets as well to the database: AAPL, MSFT, NVDA, TSLA, BTC, ETH, and SOL. 

At this point the train of thought also lead me to incorporate the first external API integration. Decided to use Alpha Vantage this time around, providing both stock and cryptocurrency market data. 

Tests and trials have been done with the API key. Relating endpoints, database and functions seem to be working fine. Tests will be added later however to be more sure. 

A problem however was noticed from using the free API key provided by Alpha Vantage, 25 requests seem to be pretty tight, considering that this project is meant to be deployed. Will a paid API key be needed in the future? We don't know yet, however the next plan is to introduce caching to at least try to reduce usage of the limited 25 requests. 

Signed 13th Commit: "Feat: Added Asset Models and Alpha Vantage Market Data Integration"

Caching implementation was successful. Since the free API key only allows 25 requests per day, we incorporated an in-memory caching mechanism with a TTL of 60 minutes. The aforementioned TTL can and could be changed depending on how we see it working in the future but it's set to 60 minutes for now. 

Instead of repeatedly trying to request the same type of information from Alpha Vantage, the caching system should be able to reduce unnecessary access to the API key and give out stored cached information if available. For added security, rate limiting is also being considered at the moment but for this specific situation caching seems to be enough for now. 

Added automated tests as well using pytest and monkeypatch to simulate market data without making actual Alpha Vantage requests. Cache hits, misses, expiration etc. All new tests passed, bringing the total to 21. 

The integration of the asset catalog and market data into FastAPI has also been successful, added the new endpoints that are responsible for each and tested via Swagger UI. Both have been confirmed to be working not only in pytest (4 more tests, giving a total of 25 tests) but hands on as well. 

Further improvements will probably include more robust caching, provider error handling and eventually Redis. But for now, the project shall move toward implementing virtual buying and selling. 

Signed: 14th Commit "Feat: Add Cached Market Data and Asset Endpoints"

While working on the virtual trading system, I realized that the main.py file was already becoming too cluttered and responsible for too many things at once, hence the files and code was reorganized for continuous future configurations and easier navigation. 

Back to the virtual trading system, first thing was to create a trade model to keep records of every purchase or sale, separate from the user's current holdings. Added the necessary constraints as well as foreign keys then generated and applied the 4th alembic migration. Implemented PostgreSQL row locking to protect against simultaneous purchases, alongside weighted-average cost calculations for repeated purchases of the same asset.

In terms of endpoints, the first buying endpoint has also been created. The endpoint retrieves market prices through the already existing Alpha Vantage integration, ensures the user has enough virtual cash, updates their holdings and then records the transaction. All database changes are committed together. 

Added five automated trading tests covering successful purchases, insufficient funds, repeated purchases of the same asset, database rollback and purchases below the minimum amount (minimum amount set to 1 dollar). Pytest and monkeypatch have been used to simulate market prices without making real Alpha Vantage requests.

A lot was done and reorganized but that about sums up the important things for this commit. I was having troubles deciding where and when to commit this time around so I'm glad that everything worked out so far. 

Most of the code won't and don't have comments but if you see some that do have, then that would be for additional future self guard for code that took a bit longer to digest. Some work also remains unfinished in regards to the buying system, which will of course be polished before moving on to selling and trade history endpoints. 

Signed: 15th Commit "Feat: Implement Virtual Buying and Refactor Backend Architecture"

Removed the content within one of the pre existing __init__ files, minor chore.  

Signed: 16th Commit "Chore: Remove Unused Console Entry Point"