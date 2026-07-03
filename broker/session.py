import warnings
from NorenRestApiPy.NorenApi import NorenApi

import sys, os
_broker_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _broker_root not in sys.path:
    sys.path.insert(0, _broker_root)
from db import read_credentials

warnings.filterwarnings("ignore")


def login_shoonya(cred):
    class ShoonyaApiPy(NorenApi):
        def __init__(self):
            super().__init__(
                host='https://trade.shoonya.com/NorenWClientWeb/',
                websocket='wss://trade.shoonya.com/NorenWSWeb/'
            )

    api = ShoonyaApiPy()
    ret = api.set_session(
        userid=cred['username'][0],
        password=cred['pwd'][0],
        usertoken=cred['sessionkey'][0]
    )
    if not ret:
        raise Exception(f"Shoonya {cred['username'][0]} login failed")
    return api


def login_flattrade(cred):
    class FlatTradeApiPy(NorenApi):
        def __init__(self):
            super().__init__(
                host='https://piconnect.flattrade.in/PiConnectTP/',
                websocket='wss://piconnect.flattrade.in/PiConnectWSTp/'
            )

    api = FlatTradeApiPy()
    ret = api.set_session(
        userid=cred['username'][0],
        password=cred['pwd'][0],
        usertoken=cred['sessionkey'][0]
    )
    if not ret:
        raise Exception(f"Flattrade {cred['username'][0]} login failed")
    return api


def broker_login(brokername, username):
    cred = read_credentials(brokername.upper(), username)
    if cred is None or cred.empty:
        raise ValueError(f"No credentials found for {brokername}/{username}")

    if brokername.lower() == "shoonya":
        return login_shoonya(cred)
    elif brokername.lower() == "flattrade":
        return login_flattrade(cred)
    else:
        raise ValueError(f"Unsupported broker: {brokername}")
