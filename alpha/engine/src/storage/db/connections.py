import asyncio
from typing import Optional
import motor.motor_asyncio
import redis.asyncio as redis
from ...utils.logger import logger, log_operation

class DatabaseConnection:
    _instance: Optional['DatabaseConnection'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self.mongo_client = None
        self.redis_client = None
        self.initialized = False

    @classmethod
    async def get_instance(cls) -> 'DatabaseConnection':
        """Get singleton instance with double-checked locking."""
        if not cls._instance:
            async with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance

    @log_operation("init_connections")
    async def initialize(self, mongo_url: str, redis_url: str):
        """Initialize database connections."""
        if self.initialized:
            logger.warning("Database connections already initialized")
            return

        logger.info("Initializing database connections")
        try:
            # Initialize MongoDB
            logger.debug("Connecting to MongoDB")
            self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_url)
            await self.mongo_client.admin.command('ping')
            logger.info("MongoDB connection successful")

            # Initialize Redis
            logger.debug("Connecting to Redis")
            self.redis_client = redis.from_url(redis_url)
            await self.redis_client.ping()
            logger.info("Redis connection successful")

            self.initialized = True
            logger.info("Database connections initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database connections: {str(e)}")
            await self.cleanup()
            raise

    @log_operation("check_connections")
    async def check_health(self) -> bool:
        """Check if database connections are healthy."""
        if not self.initialized:
            logger.warning("Database connections not initialized")
            return False

        try:
            # Check MongoDB
            logger.debug("Checking MongoDB connection")
            await self.mongo_client.admin.command('ping')

            # Check Redis
            logger.debug("Checking Redis connection")
            await self.redis_client.ping()

            logger.info("Database connections are healthy")
            return True

        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            return False

    @log_operation("cleanup_connections")
    async def cleanup(self):
        """Cleanup database connections."""
        logger.info("Cleaning up database connections")
        if self.mongo_client:
            logger.debug("Closing MongoDB connection")
            self.mongo_client.close()
            self.mongo_client = None

        if self.redis_client:
            logger.debug("Closing Redis connection")
            await self.redis_client.close()
            self.redis_client = None

        self.initialized = False
        logger.info("Database connections cleaned up successfully")