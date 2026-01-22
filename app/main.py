"""
TG群链接验证工具 - FastAPI应用入口
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.db.sqlite import init_db
from app.workers.runner import task_runner
from app.services.job_service import JobService

# API路由
from app.api.routes_files import router as files_router
from app.api.routes_import import router as import_router
from app.api.routes_jobs import router as jobs_router
from app.api.routes_results import router as results_router
from app.api.routes_events import router as events_router
from app.api.routes_config import router as config_router

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format=config.LOG_FORMAT
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    logger.info("TG群链接验证工具启动中...")
    
    # 初始化数据库
    init_db()
    logger.info("数据库初始化完成")
    
    # 重置被中断的任务
    JobService.reset_interrupted_jobs()
    
    # 初始化任务运行器
    await task_runner.initialize()
    logger.info("任务运行器初始化完成")
    
    logger.info(f"服务启动完成，监听 {config.SERVER_HOST}:{config.SERVER_PORT}")
    
    yield
    
    # 关闭时
    logger.info("TG群链接验证工具关闭中...")


# 创建FastAPI应用
app = FastAPI(
    title="TG群链接验证工具",
    description="批量验证Telegram群组/频道链接有效性，提取群名",
    version="1.0.0",
    lifespan=lifespan
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(files_router)
app.include_router(import_router)
app.include_router(jobs_router)
app.include_router(results_router)
app.include_router(events_router)
app.include_router(config_router)

# 静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# 页面路由
@app.get("/")
async def index():
    """首页"""
    return FileResponse("app/static/index.html")


@app.get("/jobs")
async def jobs_page():
    """任务列表页"""
    return FileResponse("app/static/jobs.html")


@app.get("/job/{job_id}")
async def job_detail_page(job_id: int):
    """任务详情页"""
    return FileResponse("app/static/job_detail.html")


@app.get("/settings")
async def settings_page():
    """设置页"""
    return FileResponse("app/static/settings.html")


# 健康检查
@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=False
    )
