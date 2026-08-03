from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from SmartApi import SmartConnect
import pyotp
import logging
from pydantic import BaseModel

app = FastAPI(title="AI TradePro Backend - Angel One Engine")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

angel_session = None
smartApi = None

class LoginCredentials(BaseModel):
    api_key: str
    client_code: str
    password: str
    totp_secret: str

class OrderDetails(BaseModel):
    tradingsymbol: str
    symboltoken: str
    transactiontype: str
    quantity: int
    price: float = 0.0
    ordertype: str = "MARKET"

@app.post("/api/login")
def login_angel_one(creds: LoginCredentials):
    global angel_session, smartApi
    try:
        smartApi = SmartConnect(api_key=creds.api_key)
        totp = pyotp.TOTP(creds.totp_secret).now()
        data = smartApi.generateSession(creds.client_code, creds.password, totp)
        
        if data['status']:
            angel_session = data['data']
            logging.info(f"Login Successful for {creds.client_code}")
            return {"status": "success", "message": "Connected!", "jwtToken": angel_session['jwtToken']}
        else:
            raise HTTPException(status_code=401, detail=data['message'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/place-order")
def place_order(order: OrderDetails):
    if not smartApi:
        raise HTTPException(status_code=401, detail="Not logged in")
    try:
        orderparams = {
            "variety": "NORMAL",
            "tradingsymbol": order.tradingsymbol,
            "symboltoken": order.symboltoken,
            "transactiontype": order.transactiontype,
            "exchange": "NFO",
            "ordertype": order.ordertype,
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": str(order.price),
            "squareoff": "0",
            "stoploss": "0",
            "quantity": str(order.quantity)
        }
        orderId = smartApi.placeOrder(orderparams)
        return {"status": "success", "orderId": orderId}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
