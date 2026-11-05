from fastapi import FastAPI

from larp_finance.routers import users, portfolio, assets, trades


app = FastAPI()

app.include_router(users.router)
app.include_router(portfolio.router)
app.include_router(assets.router)
app.include_router(trades.router)


@app.get("/")
def root():
    return {"message": "Welcome to Larp Finance!"}
