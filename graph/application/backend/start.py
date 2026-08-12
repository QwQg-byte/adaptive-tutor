import uvicorn
from config import settings

if __name__ == '__main__':
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,  # 禁用reload避免Windows multiprocessing问题
        log_level=settings.LOG_LEVEL.lower()
    )
