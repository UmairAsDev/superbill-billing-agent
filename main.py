import sys
import uvicorn
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from controller.app import router
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)




def main():
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    print("Hello from superbill-medical-agent!")


if __name__ == "__main__":
    main()
