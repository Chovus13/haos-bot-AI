import asyncio
import logging
import os

class WebSocketLoggingHandler(logging.Handler):
    def emit(self, record):
        log_entry = self.format(record)
        level = record.levelname
        # Store the log message for later processing instead of creating task
        self.store_log(log_entry, level)
    
    def store_log(self, log_entry, level):
        # Implement a method to store logs that need to be sent
        # This could be a queue or other data structure
        pass

async def main():
    # Setup logging
    logger = logging.getLogger()
    handler = WebSocketLoggingHandler()
    logger.addHandler(handler)
    
    # Your logging code
    logger.info(f"API ključevi: key={os.getenv('API_KEY')[:4]}..., secret={os.getenv('API_SECRET')[:4]}...")
    
    # Process stored logs periodically
    while True:
        # Implement log processing here
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())