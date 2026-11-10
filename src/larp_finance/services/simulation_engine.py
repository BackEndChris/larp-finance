from decimal import Decimal, ROUND_HALF_UP


CENT = Decimal("0.01")


def calculate_buy_and_hold(
    initial_investment: Decimal,
    purchase_price: Decimal,
    final_price: Decimal,
) -> dict[str, Decimal]:

    # Step 1: Validate inputs.
    if any(
        not value.is_finite()
        for value in (
            initial_investment,
            purchase_price,
            final_price,
        )
    ):
        raise ValueError("All inputs must be finite numbers")

    if initial_investment < Decimal("1.00"):
        raise ValueError("Minimum investment is $1.00")

    if purchase_price <= 0 or final_price <= 0:
        raise ValueError("Asset prices must be positive")

    # Step 2: Calculate fractional shares.
    quantity = initial_investment / purchase_price

    # Step 3: Calculate the final investment value.
    final_value = (quantity * final_price).quantize(
        CENT,
        rounding=ROUND_HALF_UP,
    )

    # Step 4: Calculate profit or loss.
    profit_loss = final_value - initial_investment

    return {
        "quantity": quantity,
        "final_value": final_value,
        "profit_loss": profit_loss,
    }
