from fastapi import FastAPI
from mangum import Mangum

app = FastAPI(
    title="Renown Opticals API",
    description="Backend API for the Renown opticals ecommerce platform",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}


handler = Mangum(app, lifespan="off")
