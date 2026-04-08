import asyncio
import json
import logging
import os
import aio_pika
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

#configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

async def main():
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)

    #connect_robust automatically reconnects if RabbitMQ restarts
    connection = await aio_pika.connect_robust(RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()
        
        #connect to the exact same exchange the node.js app is publishing to 
        exchange = await channel.declare_exchange("market-data", aio_pika.ExchangeType.FANOUT)

        #create an exclusive queue for this worker to consume from
        queue = await channel.declare_queue('', exclusive=True)
        await queue.bind(exchange)

        logging.info("[*] Worker initialized. Waiting for live market data from RabbitMQ...")

        count = 0
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    data = json.loads(message.body.decode())
                    pair = data['pair']
                    price = data['price']

                    #update redis instantly
                    await redis_client.set(f"orderbook:{pair}:price", price)

                    #log every 50th message to avoid spamming logs
                    count += 1
                    if count % 50 == 0:
                        logging.info(f" [✓] Updated Redis Order Book: {pair} -> ${price}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
            logging.info("Worker shutting down gracefully...")