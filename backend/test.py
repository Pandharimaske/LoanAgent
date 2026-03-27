import asyncio, sys
import logging
logging.basicConfig(level=logging.INFO)
sys.path.append('.')
from agent.helpers import classify_fields_with_llm

async def main():
    print(await classify_fields_with_llm('My name is Pranav'))

if __name__ == '__main__':
    asyncio.run(main())
