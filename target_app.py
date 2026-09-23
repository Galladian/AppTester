# target_app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time

app = FastAPI(
    title = "Demo E-Commerce Target App",
    description = "Target app for AI AppTester evaluation",
    version = "1.0.0"
)

class OrderRequest(BaseModel):
    item_id: str
    quantity: int
    user_email: str

class ReviewRequest(BaseModel):
    product_id: str
    comment: str

@app.get("/")
def home():
    return {"status": "online", "message": "Welcome to the Store API"}

@app.get("/api/products")
def get_products():
    # Flaw: Slow response time (UX/Performance Improvement)
    time.sleep(1.2)
    return [
        {"id": "p1", "name": "Wireless Mouse", "price": 29.99},
        {"id": "p2", "name": "Mechanical Keyboard", "price": 89.99}
    ]

@app.post("/api/checkout")
def checkout(order: OrderRequest):
    # Bug: Server crashes if quantity is negative or 0 (500 Error) 
    if order.quantity <= 0:
        raise Exception("Unhandled internal server crash: invalid quantity parameter!")
    
    # Bug: Accepts negative/zero amount without charging (Business Logic Flaw)
    return {"status": "success", "order_id": "ORD-12345", "charged": order.quantity * 10}

@app.post("/api/reviews")
def add_review(review: ReviewRequest):
    # Flaw: Poor unhelpful error message (Improvement)
    if not review.comment:
        return {"err": 1}
    
    return {"status": "review_added"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)