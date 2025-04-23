from fastapi import FastAPI, Query, HTTPException
from pymongo import MongoClient
from bson import ObjectId
from fastapi.middleware.cors import CORSMiddleware
import re
import os
from typing import List

app = FastAPI()

# Configure CORS properly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development, restrict in production
    allow_methods=["*"],
    allow_headers=["*"]
)

# Use environment variables for MongoDB credentials
MONGODB_URI = "mongodb+srv://gouravbasoya3:6fU2JcfOWJ3FQUd3@grocery.ikbmetg.mongodb.net/"

try:
    client = MongoClient(MONGODB_URI)
    db = client["groceries"]
    collection = db["new_products"]
    
    # Create a compound text index if it doesn't exist
    existing_indexes = collection.index_information()
    if not any(idx.get('textIndexVersion') for idx in existing_indexes.values()):
        collection.create_index([
            ("search_tags", "text"),
            ("item_name", "text"),
            ("brand_name", "text")
        ], name="text_search_index")
        
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    raise

def convert_objectid(doc):
    if doc and '_id' in doc:
        doc["_id"] = str(doc["_id"])
    return doc

def parse_quantity_input(input_str):
    """Convert user input like 1kg, 500g, 1l, 500ml to appropriate values"""
    try:
        input_str = input_str.lower().strip()
        
        # Weight conversions
        if 'kg' in input_str:
            return {'type': 'weight', 'value_kg': float(input_str.replace('kg', ''))}
        elif 'g' in input_str:
            return {'type': 'weight', 'value_kg': float(input_str.replace('g', '')) / 1000}
        
        # Volume conversions
        elif 'l' in input_str:
            return {'type': 'volume', 'value_ml': float(input_str.replace('l', '')) * 1000}
        elif 'ml' in input_str:
            return {'type': 'volume', 'value_ml': float(input_str.replace('ml', ''))}
        
        # Default case (assume kg if no unit)
        return {'type': 'weight', 'value_kg': float(input_str)}
    except:
        return None

@app.get("/search")
async def search_products(
    q: str = Query(..., description="Search in Hindi, English or with units like 1kg, 500g, 1l, 500ml"),
    category: str = Query(None, description="Filter by category"),
    min_price: float = Query(None, description="Minimum price filter"),
    max_price: float = Query(None, description="Maximum price filter")
):
    try:
        base_query = {}
        search_text = q
        quantity = None
        
        # First try to extract quantity from search query
        quantity_terms = ["kg", "g", "l", "ml"]
        if any(term in q.lower() for term in quantity_terms):
            # Try to find a quantity pattern in the query
            quantity_pattern = re.compile(r'(\d+\.?\d*)\s*(kg|g|l|ml)', re.IGNORECASE)
            match = quantity_pattern.search(q)
            if match:
                quantity_str = f"{match.group(1)}{match.group(2)}"
                quantity = parse_quantity_input(quantity_str)
                search_text = q.replace(quantity_str, "").strip()
        
        # If we found a quantity, add to query
        if quantity:
            if quantity['type'] == 'weight':
                base_query.update({
                    "is_liquid": False,
                    "weight_kg": {
                        "$gte": quantity['value_kg'] * 0.9,
                        "$lte": quantity['value_kg'] * 1.1
                    }
                })
            else:  # volume
                base_query.update({
                    "is_liquid": True,
                    "volume_ml": {
                        "$gte": quantity['value_ml'] * 0.9,
                        "$lte": quantity['value_ml'] * 1.1
                    }
                })
        
        # If we have remaining search text after quantity extraction
        if search_text:
            base_query["$text"] = {"$search": search_text}
        
        # Apply category filter if provided
        if category:
            base_query["category"] = category.lower()
        
        # Apply price range filter if provided
        price_query = {}
        if min_price is not None:
            price_query["$gte"] = min_price
        if max_price is not None:
            price_query["$lte"] = max_price
        if price_query:
            base_query["price"] = price_query
        
        # Execute the query
        if not base_query:  # If no filters, return empty
            return {"results": []}
            
        results = list(collection.find(base_query).limit(50))
        
        return {"results": [convert_objectid(doc) for doc in results]}
        
    except Exception as e:
        print(f"Search error for query '{q}': {str(e)}")  # Log the error
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.get("/categories")
async def get_categories():
    try:
        categories = collection.distinct("category")
        return {"categories": sorted(categories)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))