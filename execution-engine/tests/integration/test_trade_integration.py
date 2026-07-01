from decimal import Decimal
import pytest
from fastapi import HTTPException

async def test_register_new_user(http_client):
    response = await http_client.post("/api/v1/auth/register", json={
        "email": "trader@test.com",
        "password": "securepass123"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "trader@test.com"
    assert "id" in data
    assert "password" not in data

async def test_login_return_jwt(http_client):
    response = await http_client.post("/api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    
async def test_get_portfolio_empty(http_client):
    #first get the access token by logging in 
    login_response = await http_client.post("api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    access_token = login_response.json()["access_token"]
    portfolio_response = await http_client.get("api/v1/trading/portfolio", headers={"Authorization":f"Bearer {access_token}"})
    assert portfolio_response.status_code == 200
    assert portfolio_response.json() == []  # Expecting an empty portfolio for a new user

async def test_fund_test_account(http_client):
    login_response = await http_client.post("api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    access_token = login_response.json()["access_token"]
    fund_response = await http_client.post("api/v1/trading/faucet", headers={"Authorization":f"Bearer {access_token}"})
    assert fund_response.status_code == 200
    portfolio_response = await http_client.get("api/v1/trading/portfolio", headers={"Authorization":f"Bearer {access_token}"})
    assert portfolio_response.json()[0]["asset_symbol"] == "USD"
    assert Decimal(portfolio_response.json()[0]["balance"]) == Decimal("100000") 

async def test_execute_trade_buy(http_client, redis_client):
    login_response = await http_client.post("api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    access_token = login_response.json()["access_token"]
    await redis_client.set("orderbook:BTC-USD:price", "65000")
    trade_response = await http_client.post("api/v1/trading/execute", json={
        "type": "BUY",
        "pair": "BTC-USD",
        "amount": 1,
    }, headers={"Authorization":f"Bearer {access_token}"})
    portfolio_response = await http_client.get("api/v1/trading/portfolio", headers={"Authorization":f"Bearer {access_token}"})
    assert trade_response.status_code == 200
    assert portfolio_response.json()[1]["asset_symbol"] == "BTC" 
    assert Decimal(portfolio_response.json()[1]["balance"]) == Decimal(trade_response.json()["amount"])
    assert portfolio_response.json()[0]["asset_symbol"] == "USD"
    live_redis_price = await redis_client.get("orderbook:BTC-USD:price")
    price = Decimal(live_redis_price.decode())
    assert Decimal(portfolio_response.json()[0]["balance"]) == Decimal(Decimal(100000) - (Decimal(trade_response.json()["amount"]) * price))

async def test_execute_trade_sell(http_client, redis_client):
    await redis_client.set("orderbook:BTC-USD:price", "65000")
    login_response = await http_client.post("api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    access_token = login_response.json()["access_token"]
    portfolio_response = await http_client.get("api/v1/trading/portfolio", headers={"Authorization":f"Bearer {access_token}"})
    btc_balance = portfolio_response.json()[1]["balance"]    
    usd_balance = portfolio_response.json()[0]["balance"]    
    trade_response = await http_client.post("api/v1/trading/execute", json={
        "type": "SELL",
        "pair": "BTC-USD",
        "amount": 0.5,
    }, headers={"Authorization":f"Bearer {access_token}"})
    portfolio_response = await http_client.get("api/v1/trading/portfolio", headers={"Authorization":f"Bearer {access_token}"})
    assert trade_response.status_code == 200
    assert portfolio_response.json()[1]["asset_symbol"] == "BTC" 
    assert Decimal(portfolio_response.json()[1]["balance"]) == Decimal(btc_balance) - Decimal(trade_response.json()["amount"])
    assert portfolio_response.json()[0]["asset_symbol"] == "USD"
    live_redis_price = await redis_client.get("orderbook:BTC-USD:price")
    price = Decimal(live_redis_price.decode())
    assert Decimal(portfolio_response.json()[0]["balance"]) == Decimal(Decimal(usd_balance) + (Decimal(trade_response.json()["amount"]) * price))

async def test_buy_with_unsufficient_fund(http_client):
    login_response = await http_client.post("api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    access_token = login_response.json()["access_token"]
    trade_response = await http_client.post("api/v1/trading/execute", json={
        "type": "BUY",
        "pair": "BTC-USD",
        "amount": 5,
    }, headers={"Authorization":f"Bearer {access_token}"})
    assert trade_response.status_code == 400
    assert trade_response.json()["detail"] == "Insufficient funds"
    
async def test_sell_without_sufficient_asset_funds(http_client):
    login_response = await http_client.post("api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    access_token = login_response.json()["access_token"]
    trade_response = await http_client.post("api/v1/trading/execute", json={
        "type": "SELL",
        "pair": "BTC-USD",
        "amount": 5,
    }, headers={"Authorization":f"Bearer {access_token}"})
    assert trade_response.status_code == 400
    assert trade_response.json()["detail"] == "Insufficient asset balance"

async def test_trade_without_redis_price(http_client, redis_client):
    login_response = await http_client.post("api/v1/auth/login", data={
        "username": "trader@test.com",
        "password": "securepass123"
    })
    access_token = login_response.json()["access_token"]
    pair = "XRP-USD"
    trade_response = await http_client.post("api/v1/trading/execute", json={
        "type": "BUY",
        "pair": pair,
        "amount": 0.01,
    }, headers={"Authorization":f"Bearer {access_token}"})
    assert trade_response.status_code == 503
    assert f"No live price available for {pair}" in trade_response.json()["detail"]
    