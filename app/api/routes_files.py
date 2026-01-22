"""
TG群链接验证工具 - 文件上传API
"""
import os
import uuid
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from app.config import UPLOAD_DIR
from app.models.schemas import MessageResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["文件"])


@router.post("/upload", response_model=dict)
async def upload_file(file: UploadFile = File(...)):
    """
    上传文件
    
    支持的格式: .txt
    文件将保存到 data/uploads 目录
    """
    # 验证文件类型
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="只支持.txt文件")
    
    # 生成唯一文件名
    ext = Path(file.filename).suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    filepath = UPLOAD_DIR / unique_name
    
    try:
        # 保存文件
        content = await file.read()
        with open(filepath, 'wb') as f:
            f.write(content)
        
        file_size = len(content)
        
        logger.info(f"文件上传成功: {file.filename} -> {unique_name}, 大小: {file_size}")
        
        return {
            "success": True,
            "filename": unique_name,
            "original_name": file.filename,
            "size": file_size
        }
        
    except Exception as e:
        logger.exception(f"文件上传失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.get("/list")
async def list_files():
    """列出已上传的文件"""
    files = []
    
    for filepath in UPLOAD_DIR.iterdir():
        if filepath.is_file():
            stat = filepath.stat()
            files.append({
                "filename": filepath.name,
                "size": stat.st_size,
                "created_at": stat.st_ctime
            })
    
    # 按创建时间倒序
    files.sort(key=lambda x: x['created_at'], reverse=True)
    
    return {"files": files}


@router.delete("/{filename}")
async def delete_file(filename: str):
    """删除已上传的文件"""
    filepath = UPLOAD_DIR / filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    
    try:
        filepath.unlink()
        logger.info(f"文件删除成功: {filename}")
        return MessageResponse(message="文件删除成功", success=True)
    except Exception as e:
        logger.exception(f"文件删除失败: {e}")
        raise HTTPException(status_code=500, detail=f"文件删除失败: {str(e)}")
