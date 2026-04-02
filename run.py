import uvicorn
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
if __name__ == "__main__":
    uvicorn.run(
        "app.presentation.api.app:app",
        host="0.0.0.0",
        port=8001,
        reload=True
    )
