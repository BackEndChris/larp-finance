from sqlalchemy.dialects.postgresql import insert

from larp_finance.database import SessionLocal
from larp_finance.models import Asset


INITIAL_ASSETS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "asset_type": "stock"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "asset_type": "stock"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "asset_type": "stock"},
    {"symbol": "TSLA", "name": "Tesla, Inc.", "asset_type": "stock"},
    {"symbol": "BTC", "name": "Bitcoin", "asset_type": "crypto"},
    {"symbol": "ETH", "name": "Ethereum", "asset_type": "crypto"},
    {"symbol": "SOL", "name": "Solana", "asset_type": "crypto"},
]


def seed_assets():
    with SessionLocal() as db:
        statement = insert(Asset).values(INITIAL_ASSETS)

        statement = statement.on_conflict_do_nothing(
            index_elements=["symbol", "asset_type"],
        )

        db.execute(statement)
        db.commit()

    print("Asset seeding completed.")


if __name__ == "__main__":
    seed_assets()
