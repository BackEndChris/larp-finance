from fastapi import FastAPI

from larp_finance.routers import users, portfolio, assets, trades, tasks, simulations


app = FastAPI(
    title="LARP Finance",
    description="Virtual USD trading and asynchronous historical investment simulations. No real money or trade execution.",
    version="0.1.0",
)

app.include_router(users.router)
app.include_router(portfolio.router)
app.include_router(assets.router)
app.include_router(trades.router)
app.include_router(tasks.router)
app.include_router(simulations.router)


@app.get("/")
def root():
    return {"message": "Welcome to Larp Finance!"}
