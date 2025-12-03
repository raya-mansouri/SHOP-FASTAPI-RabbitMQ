## **Goal**

Build a simple backend service for handling product orders using:

* **Python \+ FastAPI**

* **PostgreSQL**

* **Redis**

* **RabbitMQ**

The focus is on backend architecture, correct usage of async processing, caching, and database design. No frontend is required.

---

## **Requirements**

### **1\. Database Design (PostgreSQL)**

Design and implement these tables:

#### **`products`**

* id

* name

* price

* stock

* created\_at

#### **`orders`**

* id

* user\_id

* status (PENDING, PAID, FAILED)

* total\_price

* created\_at

#### **`order_items`**

* id

* order\_id (FK → orders.id)

* product\_id (FK → products.id)

* quantity

* unit\_price

---

### **2\. API Endpoints (FastAPI)**

Implement the following endpoints:

#### **Get list of products**

`GET /products`

#### **Create a new order**

`POST /orders`

Request body:

`{`  
  `"user_id": 1,`  
  `"items": [`  
    `{"product_id": 3, "quantity": 2},`  
    `{"product_id": 5, "quantity": 1}`  
  `]`  
`}`

Response:

* order\_id

* initial status \= `PENDING`

#### **Get order details**

`GET /orders/{id}`

Returns:

* order details

* status

* total\_price

* list of order items

#### **Simulate payment**

`POST /orders/{id}/pay`

This endpoint should simulate a payment process and push a message to RabbitMQ for background order processing.

---

### **3\. Redis Usage**

Use Redis for one or more of the following purposes:

* Cache product list or product stock levels

* Temporary shopping cart storage (optional)

* Fast lookup for frequently accessed data

---

### **4\. RabbitMQ & Worker**

When payment is triggered (`POST /orders/{id}/pay`):

* Publish a message to RabbitMQ with the `order_id`

* A background worker must consume messages and:

  1. Fetch the order from PostgreSQL

  2. Validate product stock

  3. Deduct stock from products table

  4. Calculate total price

  5. Update order status:

     * `PAID` if successful

     * `FAILED` if stock is insufficient

  6. Save final result in database

---

### **5\. Concurrency & Transactions**

* Handle race conditions properly when updating stock.

* Use database transactions and locking where needed (e.g., `SELECT FOR UPDATE`).

* Ensure data consistency even with concurrent order processing.

---

### **6\. Docker Setup**

Create a `docker-compose.yml` with:

* FastAPI app

* PostgreSQL

* Redis

* RabbitMQ

* Worker service

One command should start the whole system.

---

### **7\. Testing**

Provide at least:

* 2–3 unit or integration tests

* Basic validation tests for error cases (out of stock, invalid product ID)

---

### **8\. Documentation**

Include a `README.md` that explains:

* How to run the project

* Example API requests

* Architecture overview

* Where Redis and RabbitMQ are used

---

## **Evaluation Criteria**

The candidate will be evaluated based on:

* Code organization and structure

* Correct use of Redis (not as a primary DB)

* Correct use of RabbitMQ for async processing

* Database schema design

* Handling concurrency and race conditions

* Error handling and stability

* Clean documentation

* Docker setup quality  