from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi.staticfiles import StaticFiles
from kundali_app import app as kundali_app
from muhurat import app as muhurat_app
import os

# Create the main FastAPI app
app = FastAPI(
    title="Astrology APIs",
    description="Combined API for Kundali and Muhurat services",
    version="1.0.0"
)
app.mount("/static", StaticFiles(directory="static"), name="static")
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the Kundali app under `/kundali` prefix
app.mount("/kundali", kundali_app)

# Mount the Muhurat app under `/muhurat` prefix
app.mount("/muhurat", muhurat_app)

# Health check endpoint
@app.get("/")
def health_check():
    return {"status": "ok", "message": "Astrology APIs are running!"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
