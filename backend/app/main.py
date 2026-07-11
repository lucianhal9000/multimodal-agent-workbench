from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .services.agent import AgentService


def build_agent() -> AgentService:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    client = None
    if settings.groq_api_key:
        from openai import OpenAI

        client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1", max_retries=2, timeout=60.0)
    return AgentService(settings, client)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent()
    yield


app = FastAPI(
    title="Multimodal Agent Workbench",
    version="1.0.0",
    description="An auditable multimodal agent built for the Parallel Minds Gen AI assignment.",
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "model_provider": "configured" if settings.groq_api_key else "not_configured",
    }


@app.post("/api/run")
async def run_agent(
    query: str = Form(default=""), files: list[UploadFile] = File(default=[])
):
    try:
        return await app.state.agent.run(query.strip(), files)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="The request could not be completed. Please retry with a smaller or different file.",
        ) from exc
