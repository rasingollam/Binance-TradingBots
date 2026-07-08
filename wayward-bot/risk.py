def calculate_quantity(entry: float, sl: float, risk_amount: float):
    risk_per_unit = abs(entry - sl)

    if risk_per_unit <= 0:
        raise ValueError("Invalid entry/SL")

    return risk_amount / risk_per_unit


def round_to_step(value: float, step: float):
    return round(value - (value % step), 10)
