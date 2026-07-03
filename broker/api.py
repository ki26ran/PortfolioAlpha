import datetime
import pandas as pd

from .session import broker_login

api = None


def setup_api(brokername=None, username=None):
    global api
    api = broker_login(brokername, username)
    return api


def place_live_order(symbol, side, qty, remarks, exchange="NSE", product_type="I", price_type="MKT"):
    if api is None:
        raise RuntimeError("api not set — call setup_api() first")
    side = side.upper()
    if side not in ("LONG", "SHORT"):
        raise ValueError(f"side must be LONG or SHORT, got {side}")
    buy_or_sell = "B" if side == "LONG" else "S"
    try:
        resp = api.place_order(
            tradingsymbol=symbol,
            exchange=exchange,
            buy_or_sell=buy_or_sell,
            quantity=qty,
            discloseqty=0,
            product_type=product_type,
            price_type=price_type,
            price=0,
            trigger_price=0,
            retention="DAY",
            amo="NO",
            remarks=remarks
        )
        if not resp or not isinstance(resp, dict):
            return None
        return resp.get("norenordno")
    except Exception:
        return None


def order_status(orderid):
    if api is None:
        raise RuntimeError("api not set — call setup_api() first")
    filled_flag = 0
    avg_price = 0.0
    exec_time = None
    rejection_reason = "NA"
    try:
        order_book = api.get_order_book()
        order_book = pd.DataFrame(order_book)
        if order_book.empty:
            return filled_flag, avg_price, exec_time, rejection_reason
        order_book = order_book[order_book["norenordno"] == str(int(orderid))]
        if order_book.empty:
            return filled_flag, avg_price, exec_time, rejection_reason
        row = order_book.iloc[0]
        status = row.get("status")
        rejection_reason = row.get("rejreason", "NA")
        avg_price = float(row.get("avgprc", 0) or 0)
        norentm = row.get("norentm")
        if norentm:
            try:
                exec_time = datetime.datetime.strptime(norentm, "%H:%M:%S %d-%m-%Y")
            except Exception:
                exec_time = None
        if status == "COMPLETE":
            filled_flag = 1
        elif status == "REJECTED":
            filled_flag = 2
    except Exception:
        pass
    return filled_flag, avg_price, exec_time, rejection_reason
